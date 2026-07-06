import importlib.machinery
import pathlib
import sys
import types

from loggerplusplus import loggerplusplus


class RuntimePathHelpers:
    """
    Class utilities used to configure Python import paths at runtime.

    This is mainly used to:
    - expose backend/libs for direct imports
    - expose shared/libs as the explicit package alias `shared_libs`
    """

    logger = loggerplusplus.bind(identifier="RuntimePathHelpers")

    @classmethod
    def add_to_python_path(cls, path: pathlib.Path) -> None:
        """
        Add a directory to sys.path only once.
        """
        path_str = str(path)

        if not path.exists():
            cls.logger.error(f"Python path does not exist: {path}")
            raise RuntimeError(f"Python path does not exist: {path}")

        if path_str in sys.path:
            cls.logger.debug(f"Python path already registered: {path}")
            return

        sys.path.insert(0, path_str)
        cls.logger.info(f"Python path registered: {path}")

    @classmethod
    def register_package_alias(cls, package_name: str, package_path: pathlib.Path) -> None:
        """
        Register a physical folder as an importable Python package alias.
        """
        if not package_path.exists():
            cls.logger.error(f"Package alias path does not exist: {package_path}")
            raise RuntimeError(f"Package alias path does not exist: {package_path}")

        if not package_path.is_dir():
            cls.logger.error(f"Package alias path is not a directory: {package_path}")
            raise RuntimeError(f"Package alias path is not a directory: {package_path}")

        if package_name in sys.modules:
            cls.logger.debug(f"Package alias already registered: {package_name}")
            return

        package = types.ModuleType(package_name)
        package.__path__ = [str(package_path)]
        package.__package__ = package_name

        package.__spec__ = importlib.machinery.ModuleSpec(
            name=package_name,
            loader=None,
            is_package=True,
        )
        package.__spec__.submodule_search_locations = [str(package_path)]

        sys.modules[package_name] = package

        cls.logger.info(
            f"Package alias registered: {package_name} -> {package_path}"
        )
