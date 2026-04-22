import argparse
import sys
import os
from .config import load_config
from .git import get_branch
from .client import SanshainClient

def main():
    parser = argparse.ArgumentParser(description="Sanshain Conan CLI")
    parser.add_argument("--config", default="sanshain.yaml", help="Path to sanshain.yaml")
    
    subparsers = parser.add_subparsers(dest="command")
    
    subparsers.add_parser("provide", help="Upload local spec to Sanshain")
    subparsers.add_parser("require", help="Download required specs from Sanshain")
    
    args = parser.parse_args()
    
    if not args.command:
        parser.print_help()
        sys.exit(1)
        
    try:
        config = load_config(args.config)
        client = SanshainClient(config.sanshain_url)
        branch = get_branch()
        
        if args.command == "provide":
            provides = []
            if config.provide:
                provides.append(config.provide)
            provides.extend(config.provides)

            if not provides:
                print("No 'provide' section in config")
                if not config.best_effort:
                    sys.exit(1)
                return
            
            config_dir = os.path.dirname(os.path.abspath(args.config))
            provided = False

            def do_provide_file(p, branch, file_path, api_type):
                full_path = os.path.join(config_dir, file_path)
                if os.path.exists(full_path):
                    with open(full_path, "r") as f:
                        content = f.read()
                    effective_type = api_type or "openapi"
                    print(f"Providing {effective_type} {config.service_name} (branch: {branch})...")
                    if effective_type == "openapi":
                        client.provide(config.service_name, branch, content)
                    elif effective_type == "asyncapi":
                        client.provide_asyncapi(config.service_name, branch, content)
                    elif effective_type == "proto" or effective_type == "grpc":
                        client.provide_proto(config.service_name, branch, content)
                    return True
                else:
                    print(f"File not found: {full_path}")
                    if not config.best_effort:
                        raise Exception(f"File not found: {full_path}")
                    return False

            for p in provides:
                p_branch = p.get("branch") or branch
                if "file" in p:
                    if do_provide_file(p, p_branch, p["file"], p.get("apiType")):
                        provided = True
                
                # Backward compatibility
                if "openApiFile" in p:
                    if do_provide_file(p, p_branch, p["openApiFile"], "openapi"):
                        provided = True
                if "asyncApiFile" in p:
                    if do_provide_file(p, p_branch, p["asyncApiFile"], "asyncapi"):
                        provided = True
                if "protoFile" in p:
                    if do_provide_file(p, p_branch, p["protoFile"], "proto"):
                        provided = True

            if not provided:
                print("No specification files found to provide.")
            else:
                print("Successfully provided.")
            
        elif args.command == "require":
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
                
                print(f"Requiring {len(endpoints)} endpoints from {service_name} (branch: {req_branch}, type: {api_type or 'openapi'})...")
                os.makedirs(output_path, exist_ok=True)
                
                try:
                    if len(endpoints) > 1:
                        content = client.require_bundle(config.service_name, service_name, req_branch, endpoints, timeout, api_type)
                    else:
                        ep = endpoints[0]
                        content = client.require(config.service_name, service_name, req_branch, ep["path"], ep["method"], timeout, api_type)
                    
                    ext = "proto" if api_type == "proto" else "yaml"
                    output_file = os.path.join(output_path, f"{service_name}.{ext}")
                    with open(output_file, "w") as f:
                        f.write(content)
                    print(f"Saved to {output_file}")
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
