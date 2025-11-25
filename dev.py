#!/usr/bin/env python3
"""Development helper for python-missive.

This script mirrors the reusable features of the historical dev.py
tool (virtual environment management, quality checks, packaging,
security scans, tests...) while excluding Django-specific commands.
"""

from __future__ import annotations

import json
import os
import platform
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any, Sequence

# Load .env file if it exists
_env_file = Path(__file__).resolve().parent / ".env"
if _env_file.exists():
    try:
        from dotenv import load_dotenv
        load_dotenv(_env_file)
    except ImportError:
        # python-dotenv not installed, skip silently
        pass


BLUE = "\033[94m"
GREEN = "\033[92m"
RED = "\033[91m"
YELLOW = "\033[93m"
NC = "\033[0m"

if platform.system() == "Windows" and not os.environ.get("ANSICON"):
    BLUE = GREEN = RED = YELLOW = NC = ""


PROJECT_ROOT = Path(__file__).resolve().parent
SRC_DIR = PROJECT_ROOT / "src"
TESTS_DIR = PROJECT_ROOT / "tests"


def _resolve_venv_dir() -> Path:
    """Find the virtual env directory, preferring .venv over venv."""
    preferred_names = [".venv", "venv"]
    for name in preferred_names:
        candidate = PROJECT_ROOT / name
        if candidate.exists():
            return candidate
    return PROJECT_ROOT / preferred_names[0]


VENV_DIR = _resolve_venv_dir()
VENV_BIN = VENV_DIR / ("Scripts" if platform.system() == "Windows" else "bin")
PYTHON = VENV_BIN / ("python.exe" if platform.system() == "Windows" else "python")
PIP = VENV_BIN / ("pip.exe" if platform.system() == "Windows" else "pip")


def print_info(message: str) -> None:
    print(f"{BLUE}{message}{NC}")


def print_success(message: str) -> None:
    print(f"{GREEN}{message}{NC}")


def print_error(message: str) -> None:
    print(f"{RED}{message}{NC}", file=sys.stderr)


def print_warning(message: str) -> None:
    print(f"{YELLOW}{message}{NC}")


def run_command(cmd: Sequence[str], check: bool = True, **kwargs) -> bool:
    printable = " ".join(cmd)
    print_info(f"Running: {printable}")
    try:
        subprocess.run(cmd, check=check, cwd=PROJECT_ROOT, **kwargs)
        return True
    except subprocess.CalledProcessError as exc:
        print_error(f"Command exited with code {exc.returncode}")
        return False
    except FileNotFoundError:
        print_error(f"Command not found: {cmd[0]}")
        return False


def venv_exists() -> bool:
    return VENV_DIR.exists() and PYTHON.exists()


def ensure_venv_activation(command: str) -> None:
    """
    Re-executes this script inside the project virtualenv (.venv/venv) if present.

    Skipped for commands that manage the virtualenv itself (venv, venv-clean).
    """
    venv_management_commands = {"venv", "venv-clean"}
    if command in venv_management_commands:
        return

    if not venv_exists():
        return

    current_python = Path(sys.executable).resolve()
    desired_python = PYTHON.resolve()
    if current_python == desired_python:
        return

    print_info(
        f"Activating virtual environment at {VENV_DIR} before running '{command}'..."
    )
    env = os.environ.copy()
    env["VIRTUAL_ENV"] = str(VENV_DIR)
    env["PATH"] = f"{VENV_BIN}{os.pathsep}{env.get('PATH', '')}"

    args = [str(desired_python), str(Path(__file__).resolve()), *sys.argv[1:]]
    os.execve(str(desired_python), args, env)


def get_code_directories() -> list[str]:
    targets: list[str] = []

    if SRC_DIR.exists():
        for candidate in SRC_DIR.iterdir():
            if candidate.is_dir() and not candidate.name.endswith(".egg-info"):
                targets.append(str(candidate.relative_to(PROJECT_ROOT)))

    package_dir = PROJECT_ROOT / "python_missive"
    if package_dir.exists() and package_dir.is_dir():
        targets.append(str(package_dir.relative_to(PROJECT_ROOT)))

    if TESTS_DIR.exists():
        targets.append(str(TESTS_DIR.relative_to(PROJECT_ROOT)))

    return targets or ["."]


def get_primary_package(default: str = "python_missive") -> str:
    name = read_project_name()
    if name:
        return name.replace("-", "_")

    if SRC_DIR.exists():
        packages = sorted(p.name for p in SRC_DIR.iterdir() if p.is_dir())
        if packages:
            return packages[0].replace("-", "_")

    return default


def load_module_attribute(module_path: str) -> Any:
    """Load an attribute from a module path string.
    
    Args:
        module_path: Dot-separated path to the attribute (e.g., "tests.test_config.MISSIVE_CONFIG_PROVIDERS")
        
    Returns:
        The attribute value
        
    Raises:
        ImportError: If the module or attribute cannot be loaded
        AttributeError: If the attribute doesn't exist in the module
    """
    parts = module_path.rsplit(".", 1)
    if len(parts) == 1:
        raise ValueError(f"Invalid module path: {module_path} (must contain at least one dot)")
    
    module_name, attr_name = parts
    
    import importlib
    module = importlib.import_module(module_name)
    return getattr(module, attr_name)


def read_project_name() -> str | None:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return None

    try:
        import tomllib
    except ModuleNotFoundError:
        return None

    try:
        with pyproject.open("rb") as stream:
            data = tomllib.load(stream)
    except (tomllib.TOMLDecodeError, OSError):
        return None

    project = data.get("project")
    if isinstance(project, dict):
        name = project.get("name")
        if isinstance(name, str):
            return name

    return None


def read_project_version() -> str | None:
    pyproject = PROJECT_ROOT / "pyproject.toml"
    if not pyproject.exists():
        return None

    try:
        import tomllib
    except ModuleNotFoundError:
        return None

    try:
        with pyproject.open("rb") as stream:
            data = tomllib.load(stream)
    except (tomllib.TOMLDecodeError, OSError):
        return None

    project = data.get("project")
    if isinstance(project, dict):
        version = project.get("version")
        if isinstance(version, str):
            return version

    return None


def install_build_dependencies() -> bool:
    return run_command(
        [str(PIP), "install", "--upgrade", "pip", "setuptools", "wheel"]
    )


def task_help() -> bool:
    print(f"{BLUE}python-missive — available commands{NC}\n")
    
    # Show installation status summary
    args = sys.argv[2:]
    module_path = args[0] if args else None
    _show_installation_status(module_path=module_path)
    print("")
    
    print(f"{GREEN}Environment:{NC}")
    print("  venv              Create a local virtual environment")
    print("  install           Install the package in production mode")
    print("  install-dev       Install the package in editable mode")
    print("  venv-clean        Recreate the virtual environment")
    print("")
    
    print(f"{GREEN}Providers:{NC}")
    print("  list-providers    List providers and check dependencies/config")
    print("  list-providers-config  List all providers with their *_geo attributes")
    print("  provider-info     Display service information for a provider")
    print("")
    print(f"{GREEN}Address Backends:{NC}")
    print("  address-info      List address verification backends and their status")
    print("")
    
    print(f"{GREEN}Quality & Security:{NC}")
    print("  lint              Run flake8 and mypy")
    print("  format            Format code with black + isort")
    print("  check             Run lint/format checks or provider diagnostics")
    print("  cleanup           Detect dead code / unused imports")
    print("  fix-imports       Remove unused imports (autoflake)")
    print("  complexity        Complexity analysis (radon)")
    print("  security          Security audit (bandit, safety, pip-audit)")
    print("")
    
    print(f"{GREEN}Tests:{NC}")
    print("  test              Run pytest")
    print("  test-verbose      Run pytest with verbose output")
    print("  test-provider     Run pytest filtering on a provider name")
    print("  test_providers    Run dynamic provider tests")
    print("  test-providers-import  Test all providers can be imported and instantiated")
    print("  coverage          Run tests with coverage report")
    print("")
    
    print(f"{GREEN}Cleaning:{NC}")
    print("  clean             Remove build, bytecode, and test artifacts")
    print("  clean-build       Remove build artifacts")
    print("  clean-pyc         Remove Python bytecode")
    print("  clean-test        Remove test artifacts")
    print("")
    
    print(f"{GREEN}Packaging:{NC}")
    print("  build             Build sdist and wheel")
    print("  dist              Alias for build")
    print("  upload-test       Upload to TestPyPI")
    print("  upload            Upload to PyPI")
    print("  release           Full release pipeline (check + tests + upload)")
    print("")
    
    print(f"{GREEN}Utilities:{NC}")
    print("  show-version      Print the project version")
    print("  requirements      Generate a minimal requirements.txt")
    print("  countries-csv     Generate countries.csv from mledoze dataset")
    print("  help              Display this help")
    print("")
    
    print(f"Usage: {GREEN}python dev.py <command>{NC}")
    return True


def _show_installation_status(module_path: str | None = None) -> None:
    """Display a summary of provider installation status.
    
    Args:
        module_path: Optional module path (e.g., "tests.test_config.MISSIVE_CONFIG_PROVIDERS")
                     If None, defaults to "tests.test_config.MISSIVE_CONFIG_PROVIDERS"
    """
    if not venv_exists():
        return
    
    # Use provided module path or default
    config_path = module_path or "tests.test_config.MISSIVE_CONFIG_PROVIDERS"
    
    try:
        MISSIVE_CONFIG_PROVIDERS = load_module_attribute(config_path)
        providers_config_dict = MISSIVE_CONFIG_PROVIDERS
        providers_config = list(MISSIVE_CONFIG_PROVIDERS.keys()) if isinstance(MISSIVE_CONFIG_PROVIDERS, dict) else MISSIVE_CONFIG_PROVIDERS
    except (ImportError, AttributeError, ValueError):
        # Silently skip if config not found
        return
    
    if not providers_config:
        # Silently skip if no providers configured
        return
    
    python_exec = VENV_BIN / ("python.exe" if platform.system() == "Windows" else "python")
    
    command_lines = [
        "from python_missive.providers import load_provider_class, get_provider_name_from_path, ProviderImportError",
        "",
        "providers_config = " + repr(providers_config),
        "providers_config_dict = " + repr(providers_config_dict),
        "",
        "status_summary = []",
        "",
        "for provider_path in providers_config:",
        "    try:",
        "        provider_class = load_provider_class(provider_path)",
        "        provider_name = get_provider_name_from_path(provider_path)",
        "        provider_config = providers_config_dict.get(provider_path, {}) if isinstance(providers_config_dict, dict) else {}",
        "        provider_instance = provider_class(config=provider_config)",
        "        ",
        "        # Check packages",
        "        package_status = provider_instance.check_required_packages()",
        "        packages_ok = all(package_status.values()) if package_status else True",
        "        ",
        "        # Check config",
        "        config_status = provider_instance.check_config_keys(provider_config)",
        "        config_ok = all(config_status.values()) if config_status else True",
        "        ",
        "        status_icon = '✓' if (packages_ok and config_ok) else '✗'",
        "        status_summary.append({",
        "            'name': provider_name.upper(),",
        "            'icon': status_icon,",
        "            'packages_ok': packages_ok,",
        "            'config_ok': config_ok,",
        "            'packages_count': len([p for p in package_status.values() if p]) if package_status else 0,",
        "            'packages_total': len(package_status) if package_status else 0,",
        "            'config_count': len([c for c in config_status.values() if c]) if config_status else 0,",
        "            'config_total': len(config_status) if config_status else 0,",
        "        })",
        "    except Exception:",
        "        status_summary.append({",
        "            'name': provider_path.split('.')[-2].upper(),",
        "            'icon': '✗',",
        "            'packages_ok': False,",
        "            'config_ok': False,",
        "        })",
        "",
        "import json",
        "print(json.dumps(status_summary, indent=2))",
    ]
    
    try:
        result = subprocess.run(
            [str(python_exec), "-c", "\n".join(command_lines)],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            timeout=10,
        )
        
        if result.returncode == 0 and result.stdout:
            import json
            status_list = json.loads(result.stdout)
            
            print(f"{GREEN}Installation Status:{NC}")
            for status in status_list:
                name = status["name"]
                icon = status["icon"]
                packages_info = ""
                config_info = ""
                
                if status.get("packages_total", 0) > 0:
                    packages_info = f" | Packages: {status['packages_count']}/{status['packages_total']}"
                if status.get("config_total", 0) > 0:
                    config_info = f" | Config: {status['config_count']}/{status['config_total']}"
                
                status_color = GREEN if status["packages_ok"] and status["config_ok"] else YELLOW
                print(f"  {icon} {status_color}{name}{NC}{packages_info}{config_info}")
            
            print(f"\n  Run {GREEN}python dev.py list-providers{NC} for detailed information")
        else:
            print(f"{YELLOW}⚠ Could not check installation status{NC}")
    except Exception:
        print(f"{YELLOW}⚠ Could not check installation status{NC}")


def task_venv() -> bool:
    if venv_exists():
        print_warning("Virtual environment already exists.")
        return True

    python_cmd = "python3" if platform.system() != "Windows" else "python"
    print_info("Creating virtual environment...")
    if not run_command([python_cmd, "-m", "venv", str(VENV_DIR)]):
        return False

    print_success(f"Virtual environment created at {VENV_DIR}")
    activation = (
        f"{VENV_DIR}\\Scripts\\activate"
        if platform.system() == "Windows"
        else f"source {VENV_DIR}/bin/activate"
    )
    print_info(f"Activate it with: {activation}")
    return True


def task_install() -> bool:
    if not venv_exists() and not task_venv():
        return False

    print_info("Installing package (production)...")
    if not install_build_dependencies():
        return False

    if not run_command([str(PIP), "install", "."]):
        return False

    print_success("Installation complete.")
    return True


def task_install_dev() -> bool:
    if not venv_exists() and not task_venv():
        return False

    print_info("Installing package (development)...")
    if not install_build_dependencies():
        return False

    # Install package in editable mode
    if not run_command([str(PIP), "install", "-e", "."]):
        return False

    # Install development dependencies from requirements-dev.txt
    requirements_dev = PROJECT_ROOT / "requirements-dev.txt"
    if requirements_dev.exists():
        print_info("Installing development dependencies from requirements-dev.txt...")
        if not run_command([str(PIP), "install", "-r", str(requirements_dev)]):
            return False
    else:
        print_warning("requirements-dev.txt not found, skipping dev dependencies")

    print_success("Development installation complete.")
    return True


def task_clean_build() -> bool:
    print_info("Removing build artifacts...")
    for directory in ["build", "dist", ".eggs"]:
        path = PROJECT_ROOT / directory
        if path.exists():
            shutil.rmtree(path, ignore_errors=True)
            print(f"  Removed {directory}/")

    for egg_info in PROJECT_ROOT.glob("**/*.egg-info"):
        shutil.rmtree(egg_info, ignore_errors=True)
        print(f"  Removed {egg_info}")

    for egg in PROJECT_ROOT.glob("**/*.egg"):
        if egg.is_dir():
            shutil.rmtree(egg, ignore_errors=True)
            print(f"  Removed directory {egg}")
        else:
            egg.unlink(missing_ok=True)
            print(f"  Removed {egg}")

    return True


def task_clean_pyc() -> bool:
    print_info("Removing Python bytecode artifacts...")

    for pycache in PROJECT_ROOT.glob("**/__pycache__"):
        shutil.rmtree(pycache, ignore_errors=True)
        print(f"  Removed {pycache}")

    for pattern in ["**/*.pyc", "**/*.pyo", "**/*~"]:
        for file in PROJECT_ROOT.glob(pattern):
            file.unlink(missing_ok=True)
            print(f"  Removed {file}")

    return True


def task_clean_test() -> bool:
    print_info("Removing test artifacts...")
    artifacts = [
        ".pytest_cache",
        ".coverage",
        "htmlcov",
        ".mypy_cache",
        ".ruff_cache",
        ".tox",
        "coverage.xml",
    ]

    removed = 0
    for artifact in artifacts:
        path = PROJECT_ROOT / artifact
        if path.exists():
            if path.is_dir():
                shutil.rmtree(path, ignore_errors=True)
            else:
                path.unlink(missing_ok=True)
            print(f"  Removed {artifact}")
            removed += 1

    if removed == 0:
        print_info("No test artifacts to remove.")
    else:
        print_success(f"Removed {removed} artifact(s).")
    return True


def task_clean() -> bool:
    task_clean_build()
    task_clean_pyc()
    task_clean_test()
    print_success("Workspace clean.")
    return True


def _ensure_venv_for_task(task: str) -> bool:
    if not venv_exists():
        print_error(
            f"Virtual environment not found. Run `python dev.py install-dev` before `python dev.py {task}`."
        )
        return False
    return True


def task_test() -> bool:
    if not _ensure_venv_for_task("test"):
        return False

    pytest = VENV_BIN / ("pytest.exe" if platform.system() == "Windows" else "pytest")
    if run_command([str(pytest)]):
        print_success("Tests complete.")
        return True
    return False


def task_test_verbose() -> bool:
    if not _ensure_venv_for_task("test-verbose"):
        return False

    pytest = VENV_BIN / ("pytest.exe" if platform.system() == "Windows" else "pytest")
    if run_command([str(pytest), "-vv"]):
        print_success("Verbose tests complete.")
        return True
    return False


def task_test_provider() -> bool:
    if not _ensure_venv_for_task("test-provider"):
        return False

    args = sys.argv[2:]
    if not args:
        print_error("Usage: python dev.py test-provider <provider-name>")
        return False

    provider_name = args[0]
    pattern = provider_name.replace("-", "_")

    pytest = VENV_BIN / ("pytest.exe" if platform.system() == "Windows" else "pytest")
    cmd = [str(pytest), "-k", pattern]
    print_info(f"Running provider-specific tests with pattern '{pattern}'")
    if run_command(cmd):
        print_success(f"Provider tests for '{provider_name}' complete.")
        return True
    return False


def task_list_providers() -> bool:
    """List all providers and check their dependencies and configuration.
    
    Usage:
        python dev.py list-providers [module_path]
        
    Examples:
        python dev.py list-providers
        python dev.py list-providers tests.test_config.MISSIVE_CONFIG_PROVIDERS
    """
    if not _ensure_venv_for_task("list-providers"):
        return False

    args = sys.argv[2:]
    module_path = args[0] if args else None

    # Load providers config
    providers_config = None
    providers_config_dict = None
    
    # Use provided module path or default
    config_path = module_path or "tests.test_config.MISSIVE_CONFIG_PROVIDERS"
    
    try:
        MISSIVE_CONFIG_PROVIDERS = load_module_attribute(config_path)
        providers_config_dict = MISSIVE_CONFIG_PROVIDERS
        providers_config = list(MISSIVE_CONFIG_PROVIDERS.keys()) if isinstance(MISSIVE_CONFIG_PROVIDERS, dict) else MISSIVE_CONFIG_PROVIDERS
    except (ImportError, AttributeError, ValueError) as e:
        print_error(f"Error loading module path '{config_path}': {e}")
        if not module_path:
            print_info("Usage: python dev.py list-providers [module_path]")
            print_info("Example: python dev.py list-providers tests.test_config.MISSIVE_CONFIG_PROVIDERS")
        return False

    if not providers_config:
        print_error("No providers found in configuration.")
        return False

    # Import provider utilities
    python_exec = VENV_BIN / ("python.exe" if platform.system() == "Windows" else "python")
    
    command_lines = [
        "from python_missive.helpers import get_providers_from_config",
        "from python_missive.providers import load_provider_class, get_provider_name_from_path, ProviderImportError",
        "",
        "providers_config = " + repr(providers_config),
        "providers_config_dict = " + repr(providers_config_dict),
        "",
        "print('=' * 80)",
        "print('PROVIDERS STATUS')",
        "print('=' * 80)",
        "",
        "for provider_path in providers_config:",
        "    try:",
        "        provider_class = load_provider_class(provider_path)",
        "        provider_name = get_provider_name_from_path(provider_path)",
        "        display_name = getattr(provider_class, 'display_name', provider_class.name)",
        "        ",
        "        # Create a provider instance to use its check methods",
        "        provider_config = providers_config_dict.get(provider_path, {}) if isinstance(providers_config_dict, dict) else {}",
        "        provider_instance = provider_class(config=provider_config)",
        "        ",
        "        print(f'\\n{provider_name.upper()} ({display_name})')",
        "        print('-' * 80)",
        "        print(f'  Path: {provider_path}')",
        "        print(f'  Supported types: {provider_class.supported_types}')",
        "        ",
        "        # Check required packages using provider method",
        "        required_packages = provider_class.required_packages",
        "        if required_packages:",
        "            print(f'  Required packages: {required_packages}')",
        "            package_status = provider_instance.check_required_packages()",
        "            all_installed = True",
        "            for pkg, installed in package_status.items():",
        "                status = '✓' if installed else '✗'",
        "                print(f'    {status} {pkg}')",
        "                if not installed:",
        "                    all_installed = False",
        "            if not all_installed:",
        "                print(f'    WARNING: Some packages are missing')",
        "        else:",
        "            print('  Required packages: (none)')",
        "        ",
        "        # Check config keys using provider method",
        "        config_keys = provider_class.config_keys",
        "        if config_keys:",
        "            print(f'  Config keys: {config_keys}')",
        "            config_status = provider_instance.check_config_keys(provider_config)",
        "            all_present = True",
        "            for key, present in config_status.items():",
        "                status = '✓' if present else '✗'",
        "                print(f'    {status} {key}')",
        "                if not present:",
        "                    all_present = False",
        "            if not all_present:",
        "                print(f'    WARNING: Some config keys are missing')",
        "        else:",
        "            print('  Config keys: (none)')",
        "        ",
        "    except ProviderImportError as e:",
        "        print(f'\\nERROR: {provider_path}')",
        "        print(f'  {e}')",
        "",
        "print('\\n' + '=' * 80)",
    ]

    cmd = [str(python_exec), "-c", "\n".join(command_lines)]
    
    print_info("Checking providers status...")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode == 0


def task_list_providers_config() -> bool:
    """List all providers with their *_geo attributes.
    
    Usage:
        python dev.py list-providers-config [module_path]
        
    Examples:
        python dev.py list-providers-config
        python dev.py list-providers-config tests.test_config.MISSIVE_CONFIG_PROVIDERS
    """
    if not _ensure_venv_for_task("list-providers-config"):
        return False

    args = sys.argv[2:]
    module_path = args[0] if args else None

    # Load providers config
    providers_config = None
    providers_config_dict = None
    
    # Use provided module path or default
    config_path = module_path or "tests.test_config.MISSIVE_CONFIG_PROVIDERS"
    
    try:
        MISSIVE_CONFIG_PROVIDERS = load_module_attribute(config_path)
        providers_config_dict = MISSIVE_CONFIG_PROVIDERS
        providers_config = list(MISSIVE_CONFIG_PROVIDERS.keys()) if isinstance(MISSIVE_CONFIG_PROVIDERS, dict) else MISSIVE_CONFIG_PROVIDERS
    except (ImportError, AttributeError, ValueError) as e:
        print_error(f"Error loading module path '{config_path}': {e}")
        if not module_path:
            print_info("Usage: python dev.py list-providers-config [module_path]")
            print_info("Example: python dev.py list-providers-config tests.test_config.MISSIVE_CONFIG_PROVIDERS")
        return False

    if not providers_config:
        print_error("No providers found in configuration.")
        return False

    # Import provider utilities
    python_exec = VENV_BIN / ("python.exe" if platform.system() == "Windows" else "python")
    
    command_lines = [
        "from python_missive.providers import load_provider_class, get_provider_name_from_path, ProviderImportError",
        "",
        "providers_config = " + repr(providers_config),
        "providers_config_dict = " + repr(providers_config_dict),
        "",
        "# List of all possible geo attributes",
        "geo_attrs = [",
        "    'email_geo', 'sms_geo', 'postal_geo', 'lre_geo', 'rcs_geo',",
        "    'voice_call_geo', 'notification_geo', 'push_notification_geo', 'branded_geo'",
        "]",
        "",
        "print('=' * 80)",
        "print('PROVIDERS GEOGRAPHIC COVERAGE')",
        "print('=' * 80)",
        "",
        "for provider_path in providers_config:",
        "    try:",
        "        provider_class = load_provider_class(provider_path)",
        "        provider_name = get_provider_name_from_path(provider_path)",
        "        display_name = getattr(provider_class, 'display_name', provider_class.name)",
        "        ",
        "        print(f'\\n{provider_name.upper()} ({display_name})')",
        "        print('-' * 80)",
        "        print(f'  Path: {provider_path}')",
        "        print(f'  Supported types: {provider_class.supported_types}')",
        "        ",
        "        # Check for geo attributes",
        "        found_geo = False",
        "        for geo_attr in geo_attrs:",
        "            # Search through MRO to find the attribute",
        "            geo_value = None",
        "            for cls in provider_class.__mro__:",
        "                if geo_attr in cls.__dict__:",
        "                    attr_value = cls.__dict__[geo_attr]",
        "                    if not callable(attr_value):",
        "                        geo_value = attr_value",
        "                        break",
        "                elif hasattr(cls, geo_attr):",
        "                    attr_value = getattr(cls, geo_attr)",
        "                    if not callable(attr_value):",
        "                        geo_value = attr_value",
        "                        break",
        "            ",
        "            if geo_value is not None:",
        "                found_geo = True",
        "                if isinstance(geo_value, str):",
        "                    if geo_value == '*':",
        "                        display_value = 'Worldwide (no restrictions)'",
        "                    else:",
        "                        display_value = geo_value",
        "                elif isinstance(geo_value, (list, tuple)):",
        "                    if geo_value:",
        "                        display_value = ', '.join(str(v) for v in geo_value)",
        "                    else:",
        "                        display_value = 'Worldwide (no restrictions)'",
        "                else:",
        "                    display_value = str(geo_value)",
        "                print(f'    {geo_attr}: {display_value}')",
        "        ",
        "        if not found_geo:",
        "            print('    (no geo attributes found)')",
        "        ",
        "    except ProviderImportError as e:",
        "        print(f'\\nERROR: {provider_path}')",
        "        print(f'  {e}')",
        "",
        "print('\\n' + '=' * 80)",
    ]

    cmd = [str(python_exec), "-c", "\n".join(command_lines)]
    
    print_info("Listing providers with geographic coverage...")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode == 0


def task_provider_info() -> bool:
    """Display service information for a provider.
    
    Usage:
        python dev.py provider-info <provider> <service> [module_path]
        
    Examples:
        python dev.py provider-info smspartner sms
        python dev.py provider-info brevo email
        python dev.py provider-info smspartner sms tests.test_config.MISSIVE_CONFIG_PROVIDERS
    """
    if not _ensure_venv_for_task("provider-info"):
        return False

    args = sys.argv[2:]
    if len(args) < 2:
        print_error("Usage: python dev.py provider-info <provider> <service> [module_path]")
        print_info("Examples:")
        print_info("  python dev.py provider-info smspartner sms")
        print_info("  python dev.py provider-info brevo email")
        print_info("  python dev.py provider-info smspartner voice_call")
        return False

    provider_name = args[0].lower()
    service_type = args[1].lower()
    module_path = args[2] if len(args) > 2 else None

    service_method = service_type
    method_name = f"get_{service_method}_service_info"

    # Load providers config
    config_path = module_path or "tests.test_config.MISSIVE_CONFIG_PROVIDERS"
    
    try:
        MISSIVE_CONFIG_PROVIDERS = load_module_attribute(config_path)
        providers_config_dict = MISSIVE_CONFIG_PROVIDERS
        providers_config = list(MISSIVE_CONFIG_PROVIDERS.keys()) if isinstance(MISSIVE_CONFIG_PROVIDERS, dict) else MISSIVE_CONFIG_PROVIDERS
    except (ImportError, AttributeError, ValueError) as e:
        print_error(f"Error loading module path '{config_path}': {e}")
        if not module_path:
            print_info("Usage: python dev.py provider-info <provider> <service> [module_path]")
            print_info("Example: python dev.py provider-info smspartner sms tests.test_config.MISSIVE_CONFIG_PROVIDERS")
        return False

    if not providers_config:
        print_error("No providers found in configuration.")
        return False

    # Import provider utilities
    python_exec = VENV_BIN / ("python.exe" if platform.system() == "Windows" else "python")
    
    command_lines = [
        "import json",
        "import os",
        "from pathlib import Path",
        "from python_missive.providers import load_provider_class, get_provider_name_from_path, ProviderImportError",
        "",
        "# Load .env file if it exists",
        "_env_file = Path('.env')",
        "if _env_file.exists():",
        "    try:",
        "        from dotenv import load_dotenv",
        "        load_dotenv(_env_file)",
        "    except ImportError:",
        "        pass",
        "",
        "providers_config = " + repr(providers_config),
        "providers_config_dict = " + repr(providers_config_dict),
        "provider_name = " + repr(provider_name),
        "service_type = " + repr(service_type),
        "method_name = " + repr(method_name),
        "",
        "# Find provider path by name",
        "provider_path = None",
        "for path in providers_config:",
        "    name = get_provider_name_from_path(path)",
        "    if name.lower() == provider_name or name.lower().replace('_', '') == provider_name.replace('_', ''):",
        "        provider_path = path",
        "        break",
        "",
        "if not provider_path:",
        "    print(f'ERROR: Provider \"{provider_name}\" not found in configuration')",
        "    import sys; sys.exit(1)",
        "",
        "try:",
        "    provider_class = load_provider_class(provider_path)",
        "    display_name = getattr(provider_class, 'display_name', provider_class.name)",
        "",
        "    # Create a provider instance",
        "    provider_config = providers_config_dict.get(provider_path, {}) if isinstance(providers_config_dict, dict) else {}",
        "    ",
        "    # Override with environment variables if they exist",
        "    for key in list(provider_config.keys()):",
        "        env_value = os.getenv(key)",
        "        if env_value:",
        "            provider_config[key] = env_value",
        "    # Also check for any env vars that might not be in default config",
        "    for key, value in os.environ.items():",
        "        if key.startswith(('SMSPARTNER_', 'BREVO_', 'AR24_', 'APN_', 'TWILIO_', 'VONAGE_')) and key not in provider_config:",
        "            provider_config[key] = value",
        "",
        "    provider_instance = provider_class(config=provider_config)",
        "",
        "    # Check if method exists",
        "    if not hasattr(provider_instance, method_name):",
        "        print(f'ERROR: Provider {provider_name} does not implement {method_name}')",
        "        import sys; sys.exit(1)",
        "",
        "    # Call the info method",
        "    method = getattr(provider_instance, method_name)",
        "    info = method()",
        "",
        "    # Display formatted output",
        "    print('=' * 80)",
        "    print(f'{display_name} - {service_type.upper()} Service Info')",
        "    print('=' * 80)",
        "    print('')",
        "",
        "    if isinstance(info, dict):",
        "        # Display credits",
        "        if 'credits' in info:",
        "            credits = info.get('credits')",
        "            if credits is not None:",
        "                print(f'Credits: {credits}')",
        "            else:",
        "                print('Credits: Not available')",
        "",
        "        # Display availability",
        "        if 'is_available' in info:",
        "            status = '✓ Available' if info['is_available'] else '✗ Unavailable'",
        "            print(f'Status: {status}')",
        "",
        "        # Display limits",
        "        if 'limits' in info and info['limits']:",
        "            print('Limits:')",
        "            for key, value in info['limits'].items():",
        "                print(f'  {key}: {value}')",
        "",
        "        # Display warnings",
        "        if 'warnings' in info and info['warnings']:",
        "            print('Warnings:')",
        "            for warning in info['warnings']:",
        "                print(f'  ⚠ {warning}')",
        "",
        "        # Display details (if any)",
        "        if 'details' in info and info['details']:",
        "            print('Details:')",
        "            for key, value in info['details'].items():",
        "                if isinstance(value, dict):",
        "                    print(f'  {key}:')",
        "                    for sub_key, sub_value in value.items():",
        "                        print(f'    {sub_key}: {sub_value}')",
        "                elif isinstance(value, (list, tuple)):",
        "                    print(f'  {key}: {value}')",
        "                else:",
        "                    print(f'  {key}: {value}')",
        "        elif 'details' in info and not info.get('warnings'):",
        "            # If no details but also no warnings, show raw info",
        "            print('Details: (empty)')",
        "    else:",
        "        # If not a dict, just print JSON",
        "        print(json.dumps(info, indent=2, ensure_ascii=False))",
        "",
        "    print('')",
        "    print('=' * 80)",
        "",
        "except ProviderImportError as e:",
        "    print(f'ERROR: {e}')",
        "    import sys; sys.exit(1)",
        "except Exception as e:",
        "    print(f'ERROR: {e}')",
        "    import traceback",
        "    traceback.print_exc()",
        "    import sys; sys.exit(1)",
    ]

    cmd = [str(python_exec), "-c", "\n".join(command_lines)]
    
    print_info(f"Getting {service_type} service info for {provider_name}...")
    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode == 0


def task_address_info() -> bool:
    """List address verification backends and their status.
    
    Shows which backends are configured, working, and ready to use.
    Tests backends in order until finding working ones.
    """
    if not _ensure_venv_for_task("address-info"):
        return False

    python_exec = VENV_BIN / ("python.exe" if platform.system() == "Windows" else "python")

    command_lines = [
        "import json",
        "import sys",
        "from pathlib import Path",
        "sys.path.insert(0, str(Path.cwd() / 'src'))",
        "",
        "from tests.test_config import MISSIVE_CONFIG_ADDRESS_BACKENDS",
        "from python_missive.helpers import describe_address_backends",
        "",
        "payload = describe_address_backends(MISSIVE_CONFIG_ADDRESS_BACKENDS)",
        "items = payload.get('items', [])",
        "",
        "print('=' * 80)",
        "print('ADDRESS VERIFICATION BACKENDS')",
        "print('=' * 80)",
        "print(f\"Total backends configured: {payload.get('configured', 0)}\")",
        "print(f\"Working backends: {payload.get('working', 0)}\")",
        "selected_backend = payload.get('selected_backend')",
        "if selected_backend:",
        "    print(f\"Selected backend for sample: {selected_backend}\")",
        "print()",
        "",
        "for idx, item in enumerate(items, 1):",
        "    backend_name = item.get('backend_name') or item.get('class_name')",
        "    status = item.get('status', 'unknown').capitalize()",
        "    print(f\"{idx}. {backend_name} ({item.get('class_name')})\")",
        "    print(f\"   Status: {status}\")",
        "    if item.get('error'):",
        "        print(f\"   Error: {item['error']}\")",
        "    if item.get('documentation_url'):",
        "        print(f\"   Documentation: {item['documentation_url']}\")",
        "    if item.get('site_url'):",
        "        print(f\"   Website: {item['site_url']}\")",
        "",
        "    packages = item.get('packages', {})",
        "    if packages:",
        "        print(\"   Packages:\")",
        "        for pkg, pkg_status in packages.items():",
        "            icon = '✓' if pkg_status == 'installed' else '✗'",
        "            print(f\"     - {icon} {pkg} ({pkg_status})\")",
        "    elif item.get('required_packages'):",
        "        print(\"   Packages:\")",
        "        for pkg in item['required_packages']:",
        "            print(f\"     - {pkg} (unknown)\")",
        "",
        "    config_status = item.get('config', {})",
        "    if config_status:",
        "        print(\"   Config:\")",
        "        for key, cfg in config_status.items():",
        "            present = cfg.get('present')",
        "            icon = '✓' if present else '✗'",
        "            preview = cfg.get('value_preview') or ('set' if present else 'missing')",
        "            print(f\"     - {icon} {key}: {preview}\")",
        "    print()",
        "",
        "print('Sample result:')",
        "print(json.dumps(payload.get('sample_result', {}), indent=2, ensure_ascii=False))",
        "print('=' * 80)",
    ]

    cmd = [str(python_exec), "-c", "\n".join(command_lines)]

    result = subprocess.run(cmd, cwd=PROJECT_ROOT)
    return result.returncode == 0


def task_test_providers_import() -> bool:
    """Test that all providers can be imported and instantiated.
    
    Usage:
        python dev.py test-providers-import [module_path]
        
    Examples:
        python dev.py test-providers-import
        python dev.py test-providers-import tests.test_config.MISSIVE_CONFIG_PROVIDERS
    """
    if not _ensure_venv_for_task("test-providers-import"):
        return False

    args = sys.argv[2:]
    module_path = args[0] if args else "tests.test_config.MISSIVE_CONFIG_PROVIDERS"

    script_path = PROJECT_ROOT / "scripts" / "test_providers_import.py"
    if not script_path.exists():
        print_error(f"Test script not found: {script_path}")
        return False

    python_exec = VENV_BIN / ("python.exe" if platform.system() == "Windows" else "python")
    cmd = [str(python_exec), str(script_path), module_path]
    
    print_info(f"Testing providers import from {module_path}...")
    if run_command(cmd):
        print_success("All providers import tests passed.")
        return True
    return False


def task_test_providers() -> bool:
    """Run dynamic provider tests: dev.py test_providers <provider> <service> [method]
    
    Special case: dev.py test_providers <provider> check_package_and_config
    """
    if not _ensure_venv_for_task("test-providers"):
        return False

    args = sys.argv[2:]
    if len(args) < 1:
        print_error("Usage: python dev.py test_providers <provider> [service] [method]")
        print_info("Examples:")
        print_info("  python dev.py test_providers brevo email send")
        print_info("  python dev.py test_providers brevo sms calculate_delivery_risk")
        print_info("  python dev.py test_providers apn push_notification send")
        print_info("  python dev.py test_providers brevo check_package_and_config")
        return False

    provider_name = args[0].lower()
    
    # Special case: check_package_and_config
    if len(args) >= 2 and args[1].lower() == "check_package_and_config":
        method = "check_package_and_config"
        service_type = ""  # Not needed for this method
    else:
        if len(args) < 2:
            print_error("Usage: python dev.py test_providers <provider> <service> [method]")
            return False
        service_type = args[1].lower()
        method = args[2].lower() if len(args) > 2 else "send"

    # Map service types to missive types (only if not check_package_and_config)
    if method != "check_package_and_config":
        missive_type = service_type.upper()

        # Map method names
        method_map = {
            "send": f"send_{service_type}",
            "cancel": f"cancel_{service_type}",
            "check": f"check_{service_type}_delivery_status",
            "risk": f"calculate_{service_type}_delivery_risk",
            "info": f"get_{service_type}_service_info",
        }
        method_name = method_map.get(method, method)
    else:
        method_name = "check_package_and_config"
        missive_type = None

    # Build pytest command with environment variables
    pytest = VENV_BIN / ("pytest.exe" if platform.system() == "Windows" else "pytest")
    test_file = str(TESTS_DIR / "test_providers.py")
    
    # Set environment variables for the test function
    env = os.environ.copy()
    env["TEST_PROVIDER"] = provider_name
    env["TEST_SERVICE"] = service_type
    env["TEST_METHOD"] = method
    
    cmd = [
        str(pytest),
        test_file,
        "-k",
        "test_provider_method",
        "-v",
    ]
    
    if method == "check_package_and_config":
        print_info(f"Testing {provider_name}.{method_name}()")
    else:
        print_info(f"Testing {provider_name}.{method_name}() for {service_type.upper()}")
    
    if run_command(cmd, env=env):
        print_success(f"Test complete: {provider_name} {service_type if service_type else ''} {method}")
        return True
    return False


def task_coverage() -> bool:
    if not _ensure_venv_for_task("coverage"):
        return False

    package = get_primary_package()
    pytest = VENV_BIN / ("pytest.exe" if platform.system() == "Windows" else "pytest")
    cmd = [
        str(pytest),
        f"--cov={package}",
        "--cov-report=html",
        "--cov-report=term",
    ]
    if run_command(cmd):
        print_success("Coverage report generated in htmlcov/index.html")
        return True
    return False


def task_lint() -> bool:
    if not _ensure_venv_for_task("lint"):
        return False

    flake8 = VENV_BIN / ("flake8.exe" if platform.system() == "Windows" else "flake8")
    mypy = VENV_BIN / ("mypy.exe" if platform.system() == "Windows" else "mypy")
    targets = get_code_directories()

    success = True
    if not run_command([str(flake8), *targets]):
        success = False
    if not run_command([str(mypy), *targets]):
        success = False

    if success:
        print_success("Lint checks passed.")
    return success


def task_format() -> bool:
    if not _ensure_venv_for_task("format"):
        return False

    black = VENV_BIN / ("black.exe" if platform.system() == "Windows" else "black")
    isort = VENV_BIN / ("isort.exe" if platform.system() == "Windows" else "isort")
    targets = get_code_directories()

    success = True
    if not run_command([str(black), *targets]):
        success = False
    if not run_command([str(isort), *targets]):
        success = False

    if success:
        print_success("Code formatted.")
    return success


def task_check() -> bool:
    args = sys.argv[2:]

    if args:
        if not _ensure_venv_for_task("check-provider"):
            return False

        provider_name = args[0].lower()
        service_type = args[1].lower() if len(args) > 1 else None

        providers = {
            "smspartner": ("SMS Partner", "SMSPartnerProvider"),
            "apn": ("Apple Push Notification", "APNProvider"),
            "ar24": ("AR24 (LRE)", "AR24Provider"),
            "brevo": ("Brevo", "BrevoProvider"),
        }

        if provider_name not in providers:
            print_error(
                f"Provider '{provider_name}' not supported. "
                f"Available: {', '.join(sorted(providers.keys()))}"
            )
            return False

        module_name = "python_missive.providers"
        class_name = providers[provider_name][1]

        # Try to load config from MISSIVE_CONFIG_PROVIDERS
        config_dict = {}
        try:
            MISSIVE_CONFIG_PROVIDERS = load_module_attribute("tests.test_config.MISSIVE_CONFIG_PROVIDERS")
            # Find provider config by matching class name
            for path, config in MISSIVE_CONFIG_PROVIDERS.items():
                if class_name in path or provider_name.lower() in path.lower():
                    config_dict = config
                    break
        except (ImportError, AttributeError, ValueError):
            pass

        command_lines = [
            "import json",
            "import os",
            "from pathlib import Path",
            f"from {module_name} import {class_name}",
            "",
            "# Load .env file if it exists",
            "_env_file = Path('.env')",
            "if _env_file.exists():",
            "    try:",
            "        from dotenv import load_dotenv",
            "        load_dotenv(_env_file)",
            "    except ImportError:",
            "        pass",
            "",
            "# Build config from environment variables or provided config",
            f"config = {repr(config_dict)}",
            "# Override with environment variables if they exist",
            "for key in list(config.keys()):",
            "    env_value = os.getenv(key)",
            "    if env_value:",
            "        config[key] = env_value",
            "# Also check for any env vars that might not be in default config",
            "for key, value in os.environ.items():",
            "    if key.startswith(('SMSPARTNER_', 'BREVO_', 'AR24_', 'APN_')) and key not in config:",
            "        config[key] = value",
            "",
            f"provider = {class_name}(config=config)",
        ]

        if service_type:
            method_name = f"get_{service_type}_service_info"
            command_lines.append(
                f"info = provider.{method_name}() if hasattr(provider, '{method_name}') else None"
            )
            command_lines.append(
                f"import sys; sys.exit('Unknown service type: {service_type}') if info is None else None"
            )
            command_lines.append("print(json.dumps(info, indent=2, ensure_ascii=False))")
        else:
            command_lines.append("services = getattr(provider, 'services', [])")
            command_lines.append("print(json.dumps({'available_services': services}, indent=2, ensure_ascii=False))")
            command_lines.append("import sys; sys.exit(0)")

        python_exec = VENV_BIN / ("python.exe" if platform.system() == "Windows" else "python")
        command = [str(python_exec), "-c", "\n".join(command_lines)]

        print_info(f"Checking provider '{provider_name}'...")
        # Pass environment variables (including those loaded from .env) to subprocess
        env = os.environ.copy()
        result = subprocess.run(command, cwd=PROJECT_ROOT, env=env)
        return result.returncode == 0

    # Default behaviour: lint + format checks
    if not task_lint():
        return False

    black = VENV_BIN / ("black.exe" if platform.system() == "Windows" else "black")
    isort = VENV_BIN / ("isort.exe" if platform.system() == "Windows" else "isort")
    targets = get_code_directories()

    success = True
    if not run_command([str(black), "--check", *targets]):
        success = False
    if not run_command([str(isort), "--check-only", *targets]):
        success = False

    if success:
        print_success("All checks passed.")
    return success


def task_cleanup() -> bool:
    if not _ensure_venv_for_task("cleanup"):
        return False

    vulture = VENV_BIN / ("vulture.exe" if platform.system() == "Windows" else "vulture")
    autoflake = VENV_BIN / (
        "autoflake.exe" if platform.system() == "Windows" else "autoflake"
    )
    pylint = VENV_BIN / ("pylint.exe" if platform.system() == "Windows" else "pylint")
    targets = get_code_directories()

    print_info("=" * 70)
    print_info("CLEANUP ANALYSIS")
    print_info("=" * 70)

    results = {"vulture": False, "autoflake": False, "pylint": False}

    print("\n" + "=" * 70)
    print_info("1/3 - Vulture (dead code)")
    print("=" * 70)

    if run_command([str(vulture), *targets, "--min-confidence", "80"], check=False):
        print_success("✓ Vulture: no dead code reported.")
        results["vulture"] = True
    else:
        print_warning("⚠ Vulture: review findings above.")

    print("\n" + "=" * 70)
    print_info("2/3 - Autoflake (unused imports and variables)")
    print("=" * 70)

    autoflake_cmd = [
        str(autoflake),
        "--check",
        "--recursive",
        "--remove-all-unused-imports",
        "--remove-unused-variables",
    ]
    if run_command([*autoflake_cmd, *targets], check=False):
        print_success("✓ Autoflake: nothing to clean.")
        results["autoflake"] = True
    else:
        print_warning("⚠ Autoflake: run `python dev.py fix-imports` to apply fixes.")

    print("\n" + "=" * 70)
    print_info("3/3 - Pylint (quality)")
    print("=" * 70)

    pylint_cmd = [
        str(pylint),
        *targets,
        "--fail-under=8.0",
        "--disable=C0111,C0103,R0903",
    ]
    if run_command(pylint_cmd, check=False):
        print_success("✓ Pylint: score >= 8/10.")
        results["pylint"] = True
    else:
        print_warning("⚠ Pylint: review the warnings above.")

    print("\n" + "=" * 70)
    print_info("SUMMARY")
    print("=" * 70)

    passed = sum(results.values())
    total = len(results)
    for tool, ok in results.items():
        status = f"{GREEN}✓ PASS{NC}" if ok else f"{RED}✗ FAIL{NC}"
        print(f"  {tool.upper():15} {status}")

    score = int((passed / total) * 100)
    if score == 100:
        print_success(f"Cleanup score: {score}/100 — excellent.")
    elif score >= 66:
        print_warning(f"Cleanup score: {score}/100 — acceptable.")
    else:
        print_error(f"Cleanup score: {score}/100 — needs attention.")

    return passed == total


def task_fix_imports() -> bool:
    if not _ensure_venv_for_task("fix-imports"):
        return False

    autoflake = VENV_BIN / (
        "autoflake.exe" if platform.system() == "Windows" else "autoflake"
    )
    targets = get_code_directories()

    cmd = [
        str(autoflake),
        "--in-place",
        "--recursive",
        "--remove-all-unused-imports",
        "--remove-unused-variables",
        "--remove-duplicate-keys",
        *targets,
    ]
    if run_command(cmd):
        print_success("Unused imports removed.")
        return True

    print_error("Failed to remove unused imports.")
    return False


def task_complexity() -> bool:
    if not _ensure_venv_for_task("complexity"):
        return False

    radon = VENV_BIN / ("radon.exe" if platform.system() == "Windows" else "radon")
    targets = get_code_directories()

    print_info("=" * 70)
    print_info("COMPLEXITY ANALYSIS (Radon)")
    print_info("=" * 70)

    print("\n" + "=" * 70)
    print_info("Cyclomatic Complexity (CC)")
    print("=" * 70)
    run_command([str(radon), "cc", *targets, "-s", "-a"], check=False)

    print("\n" + "=" * 70)
    print_info("Maintainability Index (MI)")
    print("=" * 70)
    run_command([str(radon), "mi", *targets, "-s"], check=False)

    print("\n" + "=" * 70)
    print_info("Raw metrics (LOC, LLOC, comments)")
    print("=" * 70)
    run_command([str(radon), "raw", *targets, "-s"], check=False)

    print_success("Complexity analysis complete.")
    return True


def task_security() -> bool:
    if not _ensure_venv_for_task("security"):
        return False

    bandit = VENV_BIN / ("bandit.exe" if platform.system() == "Windows" else "bandit")
    safety = VENV_BIN / ("safety.exe" if platform.system() == "Windows" else "safety")
    pip_audit = VENV_BIN / (
        "pip-audit.exe" if platform.system() == "Windows" else "pip-audit"
    )
    targets = get_code_directories()

    print_info("=" * 70)
    print_info("SECURITY AUDIT")
    print_info("=" * 70)

    results = {"bandit": False, "safety": False, "pip_audit": False}

    print("\n" + "=" * 70)
    print_info("1/3 - Bandit (static analysis)")
    print("=" * 70)
    if run_command([str(bandit), "-r", *targets, "-ll", "-f", "screen", "--skip", "B101"], check=False):
        print_success("✓ Bandit: no critical issues detected.")
        results["bandit"] = True
    else:
        print_warning("⚠ Bandit: review the findings above.")

    print("\n" + "=" * 70)
    print_info("2/3 - Safety (dependency vulnerabilities)")
    print("=" * 70)
    if run_command([str(safety), "check", "--json"], check=False):
        print_success("✓ Safety: no known vulnerabilities.")
        results["safety"] = True
    else:
        print_warning("⚠ Safety: check the report above.")

    print("\n" + "=" * 70)
    print_info("3/3 - pip-audit (PyPI vulnerabilities)")
    print("=" * 70)
    if run_command([str(pip_audit)], check=False):
        print_success("✓ pip-audit: no vulnerabilities reported.")
        results["pip_audit"] = True
    else:
        print_warning("⚠ pip-audit: review the report above.")

    print("\n" + "=" * 70)
    print_info("SUMMARY")
    print("=" * 70)

    passed = sum(results.values())
    total = len(results)
    for tool, ok in results.items():
        status = f"{GREEN}✓ PASS{NC}" if ok else f"{RED}✗ FAIL{NC}"
        print(f"  {tool.upper():15} {status}")

    score = int((passed / total) * 100)
    if score == 100:
        print_success(f"Security score: {score}/100 — excellent.")
    elif score >= 66:
        print_warning(f"Security score: {score}/100 — acceptable.")
    else:
        print_error(f"Security score: {score}/100 — needs attention.")

    print("\n" + BLUE + "Optional security tooling (manual setup):" + NC)
    print("  • SonarQube / SonarCloud")
    print("  • Snyk")
    print("  • OWASP Dependency-Check")

    return passed == total


def task_build() -> bool:
    if not task_clean():
        return False

    if not venv_exists() and not task_venv():
        return False
    if not install_build_dependencies():
        return False
    if not run_command([str(PIP), "install", "--upgrade", "build"]):
        return False

    python_build = VENV_BIN / (
        "python.exe" if platform.system() == "Windows" else "python"
    )
    if not run_command([str(python_build), "-m", "build"]):
        return False

    dist_dir = PROJECT_ROOT / "dist"
    if dist_dir.exists():
        for file in dist_dir.iterdir():
            size_kb = file.stat().st_size / 1024
            print(f"  {file.name} ({size_kb:.1f} KB)")

    print_success("Build complete (dist/).")
    return True


def task_dist() -> bool:
    return task_build()


def task_upload_test() -> bool:
    if not task_build():
        return False

    if not run_command([str(PIP), "install", "--upgrade", "twine"]):
        return False

    twine = VENV_BIN / ("twine.exe" if platform.system() == "Windows" else "twine")
    if not run_command([str(twine), "upload", "--repository", "testpypi", "dist/*"]):
        return False

    print_success("Upload to TestPyPI complete.")
    return True


def task_upload() -> bool:
    if not task_build():
        return False

    print_warning("WARNING: this will publish to PyPI.")
    input("Press Enter to continue, or Ctrl+C to cancel... ")

    if not run_command([str(PIP), "install", "--upgrade", "twine"]):
        return False

    twine = VENV_BIN / ("twine.exe" if platform.system() == "Windows" else "twine")
    if not run_command([str(twine), "upload", "dist/*"]):
        return False

    print_success("Upload to PyPI complete.")
    return True


def task_release() -> bool:
    if not task_check():
        return False
    if not task_test():
        return False
    if not task_upload():
        return False

    print_success("Release workflow completed.")
    return True


def task_show_version() -> bool:
    version = read_project_version()
    if version:
        print_info(f"Current version: {version}")
        return True

    print_error("Version not found in pyproject.toml")
    return False


def task_requirements() -> bool:
    requirements_file = PROJECT_ROOT / "requirements.txt"
    print_info("Writing requirements.txt...")
    with requirements_file.open("w", encoding="utf-8") as handle:
        handle.write("# Production dependencies generated automatically\n")
        handle.write("# Install with: pip install -r requirements.txt\n\n")
        handle.write("# Add your dependencies below, for example:\n")
        handle.write("# requests>=2.31.0\n")
    print_success("requirements.txt generated.")
    return True


def task_countries_csv() -> bool:
    """
    Generate a CSV of countries from mledoze dataset:
      https://raw.githubusercontent.com/mledoze/countries/refs/heads/master/dist/countries.json
    
    Usage:
      python dev.py countries-csv [output_path]
    
    Columns:
      cca2,cca3,ccn3,name_common,name_official,region,subregion,phone_codes
    """
    import csv
    import urllib.request

    args = sys.argv[2:]
    output_path = Path(args[0]).resolve() if args else (PROJECT_ROOT / "data" / "countries.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    url = "https://raw.githubusercontent.com/mledoze/countries/refs/heads/master/dist/countries.json"
    print_info(f"Downloading countries JSON from: {url}")
    try:
        with urllib.request.urlopen(url, timeout=20) as resp:
            payload = resp.read().decode("utf-8")
    except Exception as exc:
        print_error(f"Failed to download dataset: {exc}")
        return False

    try:
        items = json.loads(payload)
        if not isinstance(items, list):
            raise ValueError("Unexpected JSON structure (expected a list)")
    except Exception as exc:
        print_error(f"Failed to parse JSON: {exc}")
        return False

    def build_phone_codes(entry: dict[str, Any]) -> list[str]:
        # Prefer modern 'idd' structure; fallback to legacy 'callingCodes'
        phone_codes: list[str] = []
        idd = entry.get("idd") or {}
        root = idd.get("root")
        suffixes = idd.get("suffixes") or []
        if isinstance(root, str) and isinstance(suffixes, list) and suffixes:
            for s in suffixes:
                try:
                    phone_codes.append(f"{root}{s}")
                except Exception:
                    continue
        elif "callingCodes" in entry and isinstance(entry["callingCodes"], list):
            for cc in entry["callingCodes"]:
                if isinstance(cc, str) and cc.strip():
                    phone_codes.append(cc.strip())
        # Deduplicate and sort naturally
        return sorted({p.replace(" ", "") for p in phone_codes})

    rows: list[dict[str, str]] = []
    for entry in items:
        if not isinstance(entry, dict):
            continue
        cca2 = str(entry.get("cca2", "")).upper()
        cca3 = str(entry.get("cca3", "")).upper()
        ccn3 = str(entry.get("ccn3", "")).zfill(3) if entry.get("ccn3") else ""
        name = entry.get("name") or {}
        name_common = str(name.get("common", "")).strip()
        name_official = str(name.get("official", "")).strip()
        region = str(entry.get("region", "")).strip()
        subregion = str(entry.get("subregion", "")).strip()
        phone_codes = ";".join(build_phone_codes(entry))

        rows.append(
            {
                "cca2": cca2,
                "cca3": cca3,
                "ccn3": ccn3,
                "name_common": name_common,
                "name_official": name_official,
                "region": region,
                "subregion": subregion,
                "phone_codes": phone_codes,
            }
        )

    # Sort by name_common then cca2
    rows.sort(key=lambda r: (r["name_common"] or r["cca2"], r["cca2"]))

    with output_path.open("w", encoding="utf-8", newline="") as csvfile:
        writer = csv.DictWriter(
            csvfile,
            fieldnames=[
                "cca2",
                "cca3",
                "ccn3",
                "name_common",
                "name_official",
                "region",
                "subregion",
                "phone_codes",
            ],
        )
        writer.writeheader()
        writer.writerows(rows)

    print_success(f"Wrote {len(rows)} countries to {output_path}")
    print_info("Dataset source: https://raw.githubusercontent.com/mledoze/countries/refs/heads/master/dist/countries.json")
    return True


def task_venv_clean() -> bool:
    if venv_exists():
        print_info("Removing existing virtual environment...")
        shutil.rmtree(VENV_DIR, ignore_errors=True)
        print_success("Virtual environment removed.")
    return task_venv()


COMMANDS = {
    "help": task_help,
    "venv": task_venv,
    "install": task_install,
    "install-dev": task_install_dev,
    "venv-clean": task_venv_clean,
    "clean": task_clean,
    "clean-build": task_clean_build,
    "clean-pyc": task_clean_pyc,
    "clean-test": task_clean_test,
    "test": task_test,
    "test-verbose": task_test_verbose,
    "test-provider": task_test_provider,
    "test_providers": task_test_providers,
    "test-providers-import": task_test_providers_import,
    "list-providers": task_list_providers,
    "list-providers-config": task_list_providers_config,
    "provider-info": task_provider_info,
    "address-info": task_address_info,
    "coverage": task_coverage,
    "lint": task_lint,
    "format": task_format,
    "check": task_check,
    "cleanup": task_cleanup,
    "fix-imports": task_fix_imports,
    "complexity": task_complexity,
    "security": task_security,
    "build": task_build,
    "dist": task_dist,
    "upload-test": task_upload_test,
    "upload": task_upload,
    "release": task_release,
    "show-version": task_show_version,
    "requirements": task_requirements,
    "countries-csv": task_countries_csv,
}


def main(argv: Sequence[str] | None = None) -> int:
    args = list(argv if argv is not None else sys.argv[1:])

    if not args:
        task_help()
        return 0

    command = args[0]
    if command not in COMMANDS:
        print_error(f"Unknown command: {command}")
        print_info("Run `python dev.py help` to list available commands.")
        return 1

    ensure_venv_activation(command)

    try:
        success = COMMANDS[command]()
        return 0 if success else 1
    except KeyboardInterrupt:
        print_warning("\nOperation cancelled by user.")
        return 130
    except Exception as exc:
        print_error(f"Unexpected error: {exc}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())

