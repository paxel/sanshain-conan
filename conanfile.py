from conan import ConanFile
import os
import yaml
import time
import subprocess
import requests

class SanShain:
    def __init__(self, conanfile):
        self.conanfile = conanfile
        self.config = self._load_config()

    def _load_config(self):
        config_path = os.path.join(self.conanfile.export_sources_folder or self.conanfile.base_folder, "sanshain.yaml")
        if os.path.exists(config_path):
            with open(config_path, "r") as f:
                return yaml.safe_load(f)
        return {}

    def _get_git_branch(self):
        try:
            result = subprocess.run(["git", "rev-parse", "--abbrev-ref", "HEAD"], capture_output=True, text=True, check=True)
            return result.stdout.strip()
        except Exception as e:
            self.conanfile.output.warning(f"Failed to detect Git branch: {e}")
            return "unknown"

    def provide(self, service_name=None, openapi_file=None):
        config_provide = self.config.get("provide", {})
        service_name = service_name or config_provide.get("serviceName")
        branch = os.environ.get("SANSHAIN_BRANCH") or self._get_git_branch()
        openapi_file = openapi_file or config_provide.get("openApiFile")
        sanshain_url = self.config.get("sanshainUrl", "http://localhost:8080")

        if not service_name or not openapi_file:
            self.conanfile.output.error("serviceName and openApiFile are required for provide()")
            return

        self.conanfile.output.info(f"Providing OpenAPI for {service_name} on branch {branch} from {openapi_file} to {sanshain_url}")
        # Implementation for uploading to SanShain service would go here

    def require(self, client_name=None):
        config_require_list = self.config.get("require", [])
        require_config = None
        if len(config_require_list) == 1:
            require_config = config_require_list[0]

        if not require_config:
            self.conanfile.output.error(f"No requirement configuration found for client: {client_name or 'default'}")
            return

        client_name = client_name or self.config.get("clientName")
        requirements = require_config.get("requirements", [])
        output_dir = require_config.get("outputDirectory", os.path.join(self.conanfile.build_folder, "generated/sanshain"))
        timeout = require_config.get("timeout", 300)
        retry_interval = require_config.get("retryInterval", 10)
        sanshain_url = self.config.get("sanshainUrl", "http://localhost:8080")

        self.conanfile.output.info(f"Requiring OpenAPI snippets for {client_name} (timeout: {timeout}s)")
        
        start_time = time.time()
        while True:
            # Placeholder for actual service communication
            self.conanfile.output.info("Checking for required OpenAPI snippets...")
            all_found = True # Placeholder
            
            if all_found:
                self.conanfile.output.info("All OpenAPI snippets found.")
                break
                
            if time.time() - start_time > timeout:
                raise Exception(f"Timed out waiting for OpenAPI snippets after {timeout} seconds")
            
            self.conanfile.output.info(f"Retrying in {retry_interval} seconds...")
            time.sleep(retry_interval)

class SanShainConan(ConanFile):
    name = "sanshain-conan"
    version = "0.1.0"
    license = "AGPL-3.0"
    author = "Junie"
    url = "https://github.com/sanshain/sanshain-conan"
    description = "Conan extension for SanShain OpenAPI service"
    topics = ("openapi", "conan", "build")

    def package_info(self):
        # This is a python_requires project, so we don't need much here
        pass
