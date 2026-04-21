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
        if not self.config.provide:
            self.conanfile.output.info("Sanshain: No 'provide' configuration found")
            return

        service_name = self.config.provide["serviceName"]
        openapi_file = self.config.provide["openApiFile"]
        base_path = self.conanfile.recipe_folder or self.conanfile.base_folder
        openapi_path = os.path.join(base_path, openapi_file)
        
        if not os.path.exists(openapi_path):
            self.conanfile.output.error(f"Sanshain: OpenAPI file not found at {openapi_path}")
            return

        with open(openapi_path, "r") as f:
            content = f.read()
            
        branch = self.config.provide.get("branch") or self.branch
        self.conanfile.output.info(f"Sanshain: Providing {service_name} (branch: {branch})")
        self.client.provide(service_name, branch, content)

    def require(self):
        for req in self.config.requires:
            service_name = req["serviceName"]
            output_dir = req["outputDirectory"]
            endpoints = req["endpoints"]
            branch = req.get("branch") or self.branch
            timeout = req.get("timeout") or self.config.timeout
            
            # Resolve output_dir relative to project root
            base_output = os.path.join(self.conanfile.export_sources_folder or self.conanfile.base_folder, output_dir)
            os.makedirs(base_output, exist_ok=True)
            
            self.conanfile.output.info(f"Sanshain: Requiring {len(endpoints)} endpoints from {service_name} (branch: {branch})")
            
            if len(endpoints) > 1:
                content = self.client.require_bundle(self.config.client_name, service_name, branch, endpoints, timeout)
            else:
                ep = endpoints[0]
                content = self.client.require(self.config.client_name, service_name, branch, ep["path"], ep["method"], timeout)
                
            output_file = os.path.join(base_output, "openapi.yaml")
            with open(output_file, "w") as f:
                f.write(content)

class SanshainConan(ConanFile):
    name = "sanshain-conan"
    version = "0.1.0"
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
