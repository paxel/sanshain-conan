import argparse
import sys
import os
from .config import load_config
from .git import get_branch
from .client import SanshainClient
from .cache import SanshainCache


def main():
    parser = argparse.ArgumentParser(description="Sanshain Conan CLI")
    parser.add_argument("--config", default="sanshain.yaml", help="Path to sanshain.yaml")
    parser.add_argument("--insecure", action="store_true", help="Allow insecure SSL connections")

    subparsers = parser.add_subparsers(dest="command")

    subparsers.add_parser("provide", help="Upload local spec to Sanshain")
    subparsers.add_parser("require", help="Download required specs from Sanshain")

    args = parser.parse_args()

    if not args.command:
        parser.print_help()
        sys.exit(1)

    try:
        config = load_config(args.config)
        client = SanshainClient(config.sanshain_url, insecure=args.insecure)
        branch = get_branch()
        cache = SanshainCache()
        strict = config.strict

        if args.command == "provide":
            if not config.service_name:
                if strict:
                    print("serviceName is required (in sanshain.yaml or via environment)")
                    sys.exit(1)
                print("\u26a0 No serviceName configured. Skipping provide. Set strict: true to fail in this case.")
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
                    "\u26a0 No provide configuration found in sanshain.yaml. "
                    "Skipping. Set strict: true to fail in this case."
                )
                return

            config_dir = os.path.dirname(os.path.abspath(args.config))
            provided = False

            def do_provide_file(p, branch, file_path, api_type, base_version=None):
                full_path = os.path.join(config_dir, file_path)
                if os.path.exists(full_path):
                    with open(full_path, "r") as f:
                        content = f.read()
                    effective_type = api_type or "openapi"
                    file_key = os.path.basename(file_path)

                    # Feature 3: Client-side content caching — skip if unchanged
                    content_hash = SanshainCache.compute_hash(content)
                    cached_entry = cache.get_provide_entry(file_key)
                    if cached_entry and content_hash == cached_entry.get("content_hash"):
                        print("\u23ed Spec unchanged (hash match), skipping provide.")
                        return True

                    # Feature 1: Use cached version as base_version if not explicitly set
                    effective_base_version = base_version
                    if effective_base_version is None and cached_entry and cached_entry.get("version", 0) > 0:
                        effective_base_version = cached_entry["version"]

                    print(f"Providing {effective_type} {config.service_name} (branch: {branch})...")
                    response = None
                    if effective_type == "openapi":
                        response = client.provide(config.service_name, branch, content, effective_base_version)
                    elif effective_type == "asyncapi":
                        response = client.provide_asyncapi(config.service_name, branch, content, effective_base_version)
                    elif effective_type == "proto" or effective_type == "grpc":
                        response = client.provide_proto(config.service_name, branch, content, effective_base_version)

                    # Feature 2: Log summary and save state
                    if response and isinstance(response, dict):
                        changes = response.get("changes", {})
                        version = response.get("version", 0)
                        inserts = changes.get("inserts", 0)
                        updates = changes.get("updates", 0)
                        deletes = changes.get("deletes", 0)
                        print(
                            f"\u2713 Provided to Sanshain v{version}: {inserts} new, "
                            f"{updates} updated, {deletes} deleted endpoints"
                        )
                        response_hash = response.get("content_hash", content_hash)
                        cache.update_provide_entry(file_key, response_hash, version)
                        cache.save()

                    return True
                else:
                    print(f"File not found: {full_path}")
                    if not config.best_effort:
                        raise Exception(f"File not found: {full_path}")
                    return False

            for p in provides:
                p_branch = p.get("branch") or branch
                p_base_version = p.get("baseVersion")
                if "file" in p:
                    if do_provide_file(p, p_branch, p["file"], p.get("apiType"), p_base_version):
                        provided = True

                # Backward compatibility
                if "openApiFile" in p:
                    if do_provide_file(p, p_branch, p["openApiFile"], "openapi", p_base_version):
                        provided = True
                if "asyncApiFile" in p:
                    if do_provide_file(p, p_branch, p["asyncApiFile"], "asyncapi", p_base_version):
                        provided = True
                if "protoFile" in p:
                    if do_provide_file(p, p_branch, p["protoFile"], "proto", p_base_version):
                        provided = True

            if not provided:
                if strict:
                    print("No specification files found to provide.")
                    sys.exit(1)
                print(
                    "\u26a0 No specification files found to provide. Skipping. Set strict: true to fail in this case."
                )
            else:
                print("Successfully provided.")

        elif args.command == "require":
            if not config.service_name:
                if strict:
                    print("serviceName is required (in sanshain.yaml or via environment)")
                    sys.exit(1)
                print("\u26a0 No serviceName configured. Skipping require. Set strict: true to fail in this case.")
                return

            if not config.requires:
                if strict:
                    print("No requires configured in sanshain.yaml")
                    sys.exit(1)
                print(
                    "\u26a0 No requires configured in sanshain.yaml. Skipping. Set strict: true to fail in this case."
                )
                return

            for req in config.requires:
                service_name = req["serviceName"]
                output_dir = req["outputDirectory"]
                endpoints = req["endpoints"]
                req_branch = req.get("branch") or branch
                timeout = req.get("timeout") or config.timeout
                api_type = req.get("apiType")

                # Resolve relative to config file location
                config_dir = os.path.dirname(os.path.abspath(args.config))
                output_path = os.path.join(config_dir, output_dir)

                print(
                    f"Requiring {len(endpoints)} endpoints from {service_name} "
                    f"(branch: {req_branch}, type: {api_type or 'openapi'})..."
                )
                os.makedirs(output_path, exist_ok=True)

                try:
                    if len(endpoints) > 1:
                        cache_key = SanshainCache.require_bundle_key(service_name, req_branch)
                        cached_entry = cache.get_require_entry(cache_key)
                        cached_etag = cached_entry.get("etag") if cached_entry else None

                        result = client.require_bundle(
                            config.service_name, service_name, req_branch, endpoints, timeout, api_type, cached_etag
                        )
                    else:
                        ep = endpoints[0]
                        cache_key = SanshainCache.require_key(service_name, req_branch, ep["method"], ep["path"])
                        cached_entry = cache.get_require_entry(cache_key)
                        cached_etag = cached_entry.get("etag") if cached_entry else None

                        result = client.require(
                            config.service_name,
                            service_name,
                            req_branch,
                            ep["path"],
                            ep["method"],
                            timeout,
                            api_type,
                            cached_etag,
                        )

                    if result.get("not_modified"):
                        print(f"\u23ed {service_name} spec unchanged (304), skipping code generation.")
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
