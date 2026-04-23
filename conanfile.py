from conan import ConanFile
from conan.tools.files import copy
import os

class Sanshain:
    def __init__(self, conanfile, config_path=None):
        self.conanfile = conanfile
        # Resolve config path relative to the project root (where sanshain.yaml is expected)
        # base_folder is usually the project root in Conan 2
        base_path = conanfile.export_sources_folder or conanfile.recipe_folder or conanfile.base_folder
        config_path = config_path or os.path.join(base_path, "sanshain.yaml")
        
        # We import here to avoid issues when conanfile.py is loaded but sanshainconan is not yet in path
        try:
            from sanshainconan import load_config, get_branch, SanshainClient
        except ImportError:
            # If not in path, try adding current directory (for local testing/export)
            import sys
            current_dir = os.path.dirname(__file__)
            if current_dir not in sys.path:
                sys.path.append(current_dir)
            from sanshainconan import load_config, get_branch, SanshainClient

        self.config = load_config(config_path)
        self.client = SanshainClient(self.config.sanshain_url)
        self.branch = get_branch()

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

        def do_provide(p, branch, file_path, api_type):
            full_path = os.path.join(base_path, file_path)
            if not os.path.exists(full_path):
                self.conanfile.output.error(f"Sanshain: File not found at {full_path}")
                if not self.config.best_effort:
                    raise Exception(f"File not found: {full_path}")
                return False

            with open(full_path, "r") as f:
                content = f.read()
            
            effective_type = api_type or "openapi"
            self.conanfile.output.info(f"Sanshain: Providing {effective_type} {self.config.service_name} (branch: {branch})")
            
            if effective_type == "openapi":
                self.client.provide(self.config.service_name, branch, content)
            elif effective_type == "asyncapi":
                self.client.provide_asyncapi(self.config.service_name, branch, content)
            elif effective_type == "proto" or effective_type == "grpc":
                self.client.provide_proto(self.config.service_name, branch, content)
            return True

        for p in provides:
            branch = p.get("branch") or self.branch
            if "file" in p:
                if do_provide(p, branch, p["file"], p.get("apiType")):
                    provided = True
            
            # Backward compatibility
            if "openApiFile" in p:
                if do_provide(p, branch, p["openApiFile"], "openapi"):
                    provided = True
            if "asyncApiFile" in p:
                if do_provide(p, branch, p["asyncApiFile"], "asyncapi"):
                    provided = True
            if "protoFile" in p:
                if do_provide(p, branch, p["protoFile"], "proto"):
                    provided = True

        if provided:
            self.conanfile.output.info("Sanshain: Successfully provided spec(s)")

    def require(self):
        for req in self.config.requires:
            service_name = req["serviceName"]
            output_dir = req["outputDirectory"]
            endpoints = req["endpoints"]
            branch = req.get("branch") or self.branch
            timeout = req.get("timeout") or self.config.timeout
            api_type = req.get("apiType")
            
            # Resolve output_dir relative to project root
            base_output = os.path.join(self.conanfile.export_sources_folder or self.conanfile.base_folder, output_dir)
            os.makedirs(base_output, exist_ok=True)
            
            self.conanfile.output.info(f"Sanshain: Requiring {len(endpoints)} endpoints from {service_name} (branch: {branch}, type: {api_type or 'openapi'})")
            
            try:
                if len(endpoints) > 1:
                    content = self.client.require_bundle(self.config.service_name, service_name, branch, endpoints, timeout, api_type)
                else:
                    ep = endpoints[0]
                    content = self.client.require(self.config.service_name, service_name, branch, ep["path"], ep["method"], timeout, api_type)
                    
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

class SanshainConan(ConanFile):
    name = "sanshain-conan"
    version = "1.1.0"
    license = "AGPL-3.0"
    author = "Junie"
    url = "https://github.com/sanshain/sanshain-conan"
    description = "Conan extension for Sanshain OpenAPI service"
    topics = ("openapi", "conan", "build")
    exports_sources = "sanshainconan/*"

    def package(self):
        copy(self, "*.py", os.path.join(self.export_sources_folder, "sanshainconan"), os.path.join(self.package_folder, "sanshainconan"))

    def package_info(self):
        # python_requires don't strictly need package_info for most things
        pass
