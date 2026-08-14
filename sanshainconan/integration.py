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

from .client import SanshainClient, resolve_stream
from .config import load_config


class Sanshain:
    def __init__(self, conanfile, config_path=None):
        self.conanfile = conanfile
        # Resolve config path relative to the project root (where
        # sanshain.yaml is expected); base_folder is usually the project root
        # in Conan 2.
        base_path = conanfile.export_sources_folder or conanfile.recipe_folder or conanfile.base_folder
        config_path = config_path or os.path.join(base_path, "sanshain.yaml")

        self.config = load_config(config_path)
        self.client = SanshainClient(self.config.sanshain_url)
        # Every provide is a snapshot unless the ga switch is set
        # (SANSHAIN_GA=true). CI sets it on release pipelines; that is the
        # whole mechanism.
        self.stability = "ga" if os.environ.get("SANSHAIN_GA") == "true" else "snapshot"
        self.trunk, self.tag = resolve_stream()

    def provide(self):
        provides = []
        if self.config.provide:
            provides.append(self.config.provide)
        provides.extend(self.config.provides)

        if not provides:
            self.conanfile.output.info("Sanshain: No 'provide' configuration found")
            return

        provided = False
        base_path = self.conanfile.recipe_folder or self.conanfile.base_folder

        def do_provide(file_path, api_type):
            full_path = os.path.join(base_path, file_path)
            if not os.path.exists(full_path):
                self.conanfile.output.error(f"Sanshain: File not found at {full_path}")
                if not self.config.best_effort:
                    raise Exception(f"File not found: {full_path}")
                return False

            with open(full_path, "r") as f:
                content = f.read()

            effective_type = api_type or "openapi"
            self.conanfile.output.info(
                f"Sanshain: Providing {effective_type} {self.config.service_name} (stability: {self.stability})"
            )

            if effective_type == "openapi":
                response = self.client.provide(
                    self.config.service_name, content, self.stability, trunk=self.trunk, tag=self.tag
                )
            elif effective_type == "asyncapi":
                response = self.client.provide_asyncapi(
                    self.config.service_name, content, self.stability, trunk=self.trunk, tag=self.tag
                )
            elif effective_type == "proto" or effective_type == "grpc":
                response = self.client.provide_proto(
                    self.config.service_name, content, self.stability, trunk=self.trunk, tag=self.tag
                )
            else:
                return False
            self._report_harvest(response)
            return True

        def do_retire(api_type):
            family = api_type or "openapi"
            self.conanfile.output.info(f"Sanshain: Retiring {family} for {self.config.service_name}")
            shed = self.client.retire(self.config.service_name, family) or {}
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

            # Resolve output_dir relative to project root
            base_output = os.path.join(self.conanfile.export_sources_folder or self.conanfile.base_folder, output_dir)
            os.makedirs(base_output, exist_ok=True)

            self.conanfile.output.info(
                f"Sanshain: Requiring {len(endpoints)} endpoints from {service_name} "
                f"(version: {version}, type: {api_type or 'openapi'})"
            )

            try:
                if len(endpoints) > 1:
                    result = self.client.require_bundle(
                        self.config.service_name,
                        service_name,
                        version,
                        endpoints,
                        api_type,
                        trunk=self.trunk,
                        tag=self.tag,
                    )
                else:
                    ep = endpoints[0]
                    result = self.client.require(
                        self.config.service_name,
                        service_name,
                        version,
                        ep["path"],
                        ep["method"],
                        api_type,
                        trunk=self.trunk,
                        tag=self.tag,
                    )

                content = result["content"]
                ext = "proto" if api_type == "proto" else "yaml"
                output_file = os.path.join(base_output, f"{service_name}.{ext}")
                with open(output_file, "w") as f:
                    f.write(content)
                self.conanfile.output.info(f"Sanshain: Saved to {output_file}")
            except Exception as e:
                self.conanfile.output.error(f"Sanshain: Error requiring {service_name}: {e}")
                if not self.config.best_effort:
                    raise
                self.conanfile.output.warn("Sanshain: Continuing (best effort)")
