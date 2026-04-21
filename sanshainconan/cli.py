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
            if not config.provide:
                print("No 'provide' section in config")
                sys.exit(1)
            
            service_name = config.provide["serviceName"]
            openapi_file = config.provide["openApiFile"]
            
            # Resolve relative to config file location
            config_dir = os.path.dirname(os.path.abspath(args.config))
            openapi_path = os.path.join(config_dir, openapi_file)
            
            if not os.path.exists(openapi_path):
                print(f"OpenAPI file not found: {openapi_path}")
                sys.exit(1)
                
            with open(openapi_path, "r") as f:
                content = f.read()
                
            provided_branch = config.provide.get("branch") or branch
            print(f"Providing {service_name} (branch: {provided_branch})...")
            client.provide(service_name, provided_branch, content)
            print("Successfully provided.")
            
        elif args.command == "require":
            for req in config.requires:
                service_name = req["serviceName"]
                output_dir = req["outputDirectory"]
                endpoints = req["endpoints"]
                req_branch = req.get("branch") or branch
                timeout = req.get("timeout") or config.timeout
                
                # Resolve relative to config file location
                config_dir = os.path.dirname(os.path.abspath(args.config))
                output_path = os.path.join(config_dir, output_dir)
                
                print(f"Requiring {len(endpoints)} endpoints from {service_name} (branch: {req_branch})...")
                os.makedirs(output_path, exist_ok=True)
                
                if len(endpoints) > 1:
                    content = client.require_bundle(config.client_name, service_name, req_branch, endpoints, timeout)
                else:
                    ep = endpoints[0]
                    content = client.require(config.client_name, service_name, req_branch, ep["path"], ep["method"], timeout)
                
                output_file = os.path.join(output_path, "openapi.yaml")
                with open(output_file, "w") as f:
                    f.write(content)
                print(f"Saved to {output_file}")
                
    except Exception as e:
        print(f"Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()
