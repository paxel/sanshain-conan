"""The Conan integration: the `Sanshain` helper a consumer's conanfile drives.

Installed from PyPI (`pip install sanshain-conan`) and imported directly —
this replaced the 1.x/2.0 `python_requires` pattern, which resolved from a
Conan remote that was never stood up:

    from sanshainconan import Sanshain

    class MyPackage(ConanFile):
        def generate(self):
            sanshain = Sanshain(self)
            sanshain.provide()
            sanshain.require()

Stability and stream are read from the environment, because a `conan install`
carries no plugin flags: `SANSHAIN_GA=true` publishes GA, `SANSHAIN_TRUNK=true`
declares the trunk stream and `SANSHAIN_TAG=<branch>` a sanshain-branch. All
three are pipeline concerns and never live in `sanshain.yaml`.
"""

import os

from .catalog import run_catalog
from .client import SanshainClient, SanshainError, StrictError, resolve_origin, resolve_stream
from .config import ConfigError, env_flag, load_config, puzzled_cat


class Sanshain:
    def __init__(self, conanfile, config_path=None):
        self.conanfile = conanfile
        # Without an explicit config_path, sanshain.yaml is expected in the
        # project root; base_folder is usually the project root in Conan 2.
        if not config_path:
            root = conanfile.export_sources_folder or conanfile.recipe_folder or conanfile.base_folder
            config_path = os.path.join(root, "sanshain.yaml")

        # Every relative path in sanshain.yaml (file, outputDirectory, ...)
        # resolves against the folder the config was loaded from — one base
        # for config, provide and require, never the working directory.
        self.base_path = os.path.dirname(os.path.abspath(config_path))
        try:
            self.config = load_config(config_path)
        except ConfigError as e:
            # The cat comes first, also when the config then fails (under
            # strict, the unknown fields are the failure).
            if e.unknown_fields:
                for line in puzzled_cat(e.unknown_fields, e.strict):
                    conanfile.output.warning(line)
            raise
        if self.config.unknown_fields:
            for line in puzzled_cat(self.config.unknown_fields, False):
                conanfile.output.warning(line)
        # Every Sanshain-Warning header is a warning; under strict it fails the call.
        self.client = SanshainClient(self.config.sanshain_url, on_warning=self._warn, strict=self.config.strict)
        # Every provide is a snapshot unless the ga switch is set
        # (SANSHAIN_GA=true). CI sets it on release pipelines; that is the
        # whole mechanism.
        self.stability = "ga" if env_flag("SANSHAIN_GA") else "snapshot"
        # Why this build provides: build and change URL from the runner,
        # tickets and note from SANSHAIN_TICKETS / SANSHAIN_NOTE.
        self.origin = resolve_origin()
        try:
            self.trunk, self.tag = resolve_stream(strict=self.config.strict, warn=self._warn)
        except StrictError as e:
            conanfile.output.error(f"Sanshain: {e}")
            raise

    def _warn(self, text):
        self.conanfile.output.warning(f"Sanshain: {text}")

    def _call(self, fn, *args, **kwargs):
        """A client call; a strict failure is logged (after the call's own
        error, if it failed too) before it propagates, since Conan shows only
        the exception text."""
        try:
            return fn(*args, **kwargs)
        except StrictError as e:
            if e.error is not None:
                self.conanfile.output.error(f"Sanshain: {e.error}")
            self.conanfile.output.error(f"Sanshain: {e}")
            raise

    def provide(self):
        provides = []
        if self.config.provide:
            provides.append(self.config.provide)
        provides.extend(self.config.provides)

        if not provides:
            self.conanfile.output.info("Sanshain: No 'provide' configuration found")
            return

        provided = False

        def do_provide(file_path, api_type):
            full_path = os.path.join(self.base_path, file_path)
            if not os.path.exists(full_path):
                self.conanfile.output.error(f"Sanshain: File not found at {full_path}")
                if not self.config.best_effort:
                    raise Exception(f"File not found: {full_path}")
                return False

            with open(full_path, "r", encoding="utf-8-sig") as f:  # UTF-8, BOM stripped
                content = f.read()

            effective_type = api_type or "openapi"
            self.conanfile.output.info(
                f"Sanshain: Providing {effective_type} {self.config.service_name} (stability: {self.stability})"
            )

            if effective_type == "openapi":
                response = self._call(
                    self.client.provide,
                    self.config.service_name,
                    content,
                    self.stability,
                    trunk=self.trunk,
                    tag=self.tag,
                    origin=self.origin,
                )
            elif effective_type == "asyncapi":
                response = self._call(
                    self.client.provide_asyncapi,
                    self.config.service_name,
                    content,
                    self.stability,
                    trunk=self.trunk,
                    tag=self.tag,
                    origin=self.origin,
                )
            elif effective_type == "proto" or effective_type == "grpc":
                response = self._call(
                    self.client.provide_proto,
                    self.config.service_name,
                    content,
                    self.stability,
                    trunk=self.trunk,
                    tag=self.tag,
                    origin=self.origin,
                )
            else:
                return False
            self._report_harvest(response)
            return True

        def do_retire(api_type):
            family = api_type or "openapi"
            self.conanfile.output.info(f"Sanshain: Retiring {family} for {self.config.service_name}")
            shed = self._call(self.client.retire, self.config.service_name, family) or {}
            self.conanfile.output.info(
                "Sanshain: Retired — closed %d trunk pin(s), released %d contract(s); "
                "history and existing pins are untouched"
                % (shed.get("trunk_pins_closed", 0), shed.get("contracts_released", 0))
            )
            return True

        for p in provides:
            if p.get("retired"):
                if do_retire(p.get("apiType")):
                    provided = True
                continue
            if "file" in p:
                if do_provide(p["file"], p.get("apiType")):
                    provided = True

            # Backward compatibility
            if "openApiFile" in p:
                if do_provide(p["openApiFile"], "openapi"):
                    provided = True
            if "asyncApiFile" in p:
                if do_provide(p["asyncApiFile"], "asyncapi"):
                    provided = True
            if "protoFile" in p:
                if do_provide(p["protoFile"], "proto"):
                    provided = True

        if provided:
            self.conanfile.output.info("Sanshain: Successfully provided spec(s)")

    def catalog(self):
        """Push the `catalogInfo` file (Backstage catalog-info.yaml) to Sanshain; needs Service 2.4.0.

        Without catalogInfo it warns and skips (strict: raises). A failed push
        raises, or only warns under bestEffort; a push Sanshain did not record
        warns, or raises StrictError under strict.
        """
        output = self.conanfile.output
        try:
            self._call(run_catalog, self.config, self.client, self.base_path, self.trunk, output.info, output.warning)
        except SanshainError as e:
            if not self.config.best_effort:
                output.error(f"Sanshain: {e}")
                raise
            output.warning(f"Sanshain: {e}")
            output.warning("Sanshain: Continuing (best effort)")

    def _report_harvest(self, response):
        # Surface the harvested AsyncAPI subscriptions, or the feature is
        # invisible: a subscription expecting a field no contract guarantees
        # would only be discovered later, on the GA provide the server
        # refuses. Advisories never fail the build — that 409 is the
        # server's job.
        if not isinstance(response, dict):
            return
        for sub in response.get("harvested_subscriptions") or []:
            line = f"{sub.get('channel', '?')} / {sub.get('message_name', '?')}"
            owner = sub.get("owner")
            line += f" <- {owner}" if owner else " <- (no publisher yet)"
            drift = sub.get("drift")
            if drift:
                line += f" — {drift}"
            if drift or not owner:
                self.conanfile.output.warning(f"Sanshain: subscription {line}")
            else:
                self.conanfile.output.info(f"Sanshain: subscription {line}")

    def require(self):
        for req in self.config.requires:
            service_name = req["serviceName"]
            output_dir = req["outputDirectory"]
            endpoints = req["endpoints"]
            version = req["version"]
            api_type = req.get("apiType")
            fmt = req.get("format")

            base_output = os.path.join(self.base_path, output_dir)
            os.makedirs(base_output, exist_ok=True)

            self.conanfile.output.info(
                f"Sanshain: Requiring {len(endpoints)} endpoints from {service_name} "
                f"(version: {version}, type: {api_type or 'openapi'})"
            )

            try:
                if len(endpoints) > 1:
                    result = self._call(
                        self.client.require_bundle,
                        self.config.service_name,
                        service_name,
                        version,
                        endpoints,
                        api_type,
                        trunk=self.trunk,
                        tag=self.tag,
                        fmt=fmt,
                    )
                else:
                    ep = endpoints[0]
                    result = self._call(
                        self.client.require,
                        self.config.service_name,
                        service_name,
                        version,
                        ep["path"],
                        ep["method"],
                        api_type,
                        trunk=self.trunk,
                        tag=self.tag,
                        fmt=fmt,
                    )

                ext = "proto" if api_type == "proto" else "yaml"
                output_file = os.path.join(base_output, f"{service_name}.{ext}")
                # Binary: the server's bytes as they are, no newline translation.
                with open(output_file, "wb") as f:
                    f.write(result["body"])
                self.conanfile.output.info(f"Sanshain: Saved to {output_file}")
            except StrictError:
                raise
            except Exception as e:
                self.conanfile.output.error(f"Sanshain: Error requiring {service_name}: {e}")
                if not self.config.best_effort:
                    raise
                self.conanfile.output.warn("Sanshain: Continuing (best effort)")
