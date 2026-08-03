import argparse
import os
import sys

from .cache import SanshainCache
from .client import SanshainClient, SanshainError, VersionConflictError
from .config import load_config


def resolve_stability(ga_flag=False):
    """Every provide is a snapshot unless the ga switch is set explicitly:
    the --ga flag or the environment variable SANSHAIN_GA=true."""
    if ga_flag or os.environ.get("SANSHAIN_GA") == "true":
        return "ga"
    return "snapshot"


def format_version_conflict(error, spec_file, api_type):
    if api_type in ("proto", "grpc"):
        slot = "the // sanshain-version: marker"
    else:
        slot = "info.version"
    return (
        f"✗ Version conflict: {error.server_message}\n"
        f"  Publish as {error.proposed_version} — update {slot} in {spec_file}"
    )


def main():
    parser = argparse.ArgumentParser(description="Sanshain Conan CLI")
    parser.add_argument("--config", default="sanshain.yaml", help="Path to sanshain.yaml")
    parser.add_argument("--insecure", action="store_true", help="Allow insecure SSL connections")
    parser.add_argument("--ga", action="store_true", help="Provide as ga (immutable release); default is snapshot")
    parser.add_argument("--best-effort", action="store_true", help="Continue on errors")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("provide", help="Upload local spec to Sanshain")
    subparsers.add_parser("require", help="Download required specs from Sanshain")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        config = None
        try:
            config = load_config(args.config)
        except Exception as e:
            resolved_best_effort = args.best_effort or os.environ.get("SANSHAIN_BEST_EFFORT") == "true"
            if resolved_best_effort:
                print(f"Warning loading config: {e}")
                # Create a minimal config object
                from .config import SanshainConfig

                config = SanshainConfig({"sanshainUrl": "http://localhost:8080"})
            else:
                raise

        if args.best_effort:
            config.best_effort = True
        elif os.environ.get("SANSHAIN_BEST_EFFORT") == "true":
            config.best_effort = True

        client = SanshainClient(config.sanshain_url, insecure=args.insecure)
        strict = config.strict

        if args.command == "provide":
            if not config.service_name:
                if strict:
                    print("serviceName is required (in sanshain.yaml or via environment)")
                    sys.exit(1)
                print("⚠ No serviceName configured. Skipping provide. Set strict: true to fail in this case.")
                return

            provides = []
            if config.provide:
                provides.append(config.provide)
            provides.extend(config.provides)

            if not provides:
                if strict:
                    print("No 'provide' section in config")
                    sys.exit(1)
                print(
                    "⚠ No provide configuration found in sanshain.yaml. "
                    "Skipping. Set strict: true to fail in this case."
                )
                return

            config_dir = os.path.dirname(os.path.abspath(args.config))
            stability = resolve_stability(args.ga)
            provided = False

            def do_provide_file(file_path, api_type):
                full_path = os.path.join(config_dir, file_path)
                if not os.path.exists(full_path):
                    print(f"File not found: {full_path}")
                    if not config.best_effort:
                        raise SanshainError(f"File not found: {full_path}")
                    return False

                with open(full_path, "r") as f:
                    content = f.read()
                effective_type = api_type or "openapi"

                print(f"Providing {effective_type} {config.service_name} (stability: {stability})...")
                try:
                    if effective_type == "openapi":
                        response = client.provide(config.service_name, content, stability)
                    elif effective_type == "asyncapi":
                        response = client.provide_asyncapi(config.service_name, content, stability)
                    elif effective_type == "proto" or effective_type == "grpc":
                        response = client.provide_proto(config.service_name, content, stability)
                    else:
                        raise SanshainError(f"Unknown apiType: {effective_type}")
                except VersionConflictError as e:
                    print(format_version_conflict(e, full_path, effective_type))
                    if not config.best_effort:
                        sys.exit(1)
                    print("Continuing (best effort)")
                    return False

                if response and isinstance(response, dict):
                    changes = response.get("changes", {})
                    version = response.get("version", "?")
                    resp_stability = response.get("stability", stability)
                    inserts = changes.get("inserts", 0)
                    updates = changes.get("updates", 0)
                    deletes = changes.get("deletes", 0)
                    print(
                        f"✓ Provided {version} ({resp_stability}): {inserts} new, "
                        f"{updates} updated, {deletes} deleted endpoints"
                    )
                return True

            for p in provides:
                if "file" in p:
                    if do_provide_file(p["file"], p.get("apiType")):
                        provided = True

                # Backward compatibility
                if "openApiFile" in p:
                    if do_provide_file(p["openApiFile"], "openapi"):
                        provided = True
                if "asyncApiFile" in p:
                    if do_provide_file(p["asyncApiFile"], "asyncapi"):
                        provided = True
                if "protoFile" in p:
                    if do_provide_file(p["protoFile"], "proto"):
                        provided = True

            if not provided:
                if strict:
                    print("No specification files found to provide.")
                    sys.exit(1)
                print("⚠ No specification files found to provide. Skipping. Set strict: true to fail in this case.")
            else:
                print("Successfully provided.")

        elif args.command == "require":
            if not config.service_name:
                if strict:
                    print("serviceName is required (in sanshain.yaml or via environment)")
                    sys.exit(1)
                print("⚠ No serviceName configured. Skipping require. Set strict: true to fail in this case.")
                return

            if not config.requires:
                if strict:
                    print("No requires configured in sanshain.yaml")
                    sys.exit(1)
                print("⚠ No requires configured in sanshain.yaml. Skipping. Set strict: true to fail in this case.")
                return

            cache = SanshainCache()

            for req in config.requires:
                service_name = req["serviceName"]
                output_dir = req["outputDirectory"]
                endpoints = req["endpoints"]
                version = req["version"]
                api_type = req.get("apiType")

                # Resolve relative to config file location
                config_dir = os.path.dirname(os.path.abspath(args.config))
                output_path = os.path.join(config_dir, output_dir)

                print(
                    f"Requiring {len(endpoints)} endpoints from {service_name} "
                    f"(version: {version}, type: {api_type or 'openapi'})..."
                )
                os.makedirs(output_path, exist_ok=True)

                try:
                    if len(endpoints) > 1:
                        cache_key = SanshainCache.require_bundle_key(service_name, version)
                        cached_entry = cache.get_require_entry(cache_key)
                        cached_etag = cached_entry.get("etag") if cached_entry else None

                        result = client.require_bundle(
                            config.service_name, service_name, version, endpoints, api_type, cached_etag
                        )
                    else:
                        ep = endpoints[0]
                        cache_key = SanshainCache.require_key(service_name, version, ep["method"], ep["path"])
                        cached_entry = cache.get_require_entry(cache_key)
                        cached_etag = cached_entry.get("etag") if cached_entry else None

                        result = client.require(
                            config.service_name,
                            service_name,
                            version,
                            ep["path"],
                            ep["method"],
                            api_type,
                            cached_etag,
                        )

                    if result.get("not_modified"):
                        print(f"⏭ {service_name} spec unchanged (304), skipping code generation.")
                        continue

                    content = result["content"]
                    ext = "proto" if api_type == "proto" else "yaml"
                    output_file = os.path.join(output_path, f"{service_name}.{ext}")
                    with open(output_file, "w") as f:
                        f.write(content)
                    print(f"Saved to {output_file}")

                    if result.get("etag"):
                        cache.update_require_entry(cache_key, result["etag"])
                        cache.save()

                except Exception as e:
                    print(f"Error requiring {service_name}: {e}")
                    if not config.best_effort:
                        sys.exit(1)
                    print("Continuing (best effort)")

    except Exception as e:
        print(f"Error: {e}")
        if not config.best_effort:
            sys.exit(1)
        print("Continuing (best effort)")


if __name__ == "__main__":
    main()
