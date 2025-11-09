from PyQt5.QtGui import QIcon
from PyQt5.QtWidgets import QApplication

class GetAppIcon:
    """
    Manages application icons, caching them in memory only.
    Supports setting the application icon from a file named 'appicon.ico' located
    in the same directory as this module or from a provided path.
    """

    @staticmethod
    def set_app_icon(name: str = "Robux.ico") -> bool:
        """
        Set the application icon from a named icon file.
        Defaults to 'Robux.ico' if no name is provided.
        Returns True on success, False if the icon is not found.
        Supports .ico files via QIcon direct loading.
        """
        # Normalize name
        name = name.lower()
        if not name.endswith(".ico"):
            name += ".ico"

        icon = QIcon(str(name))
        QApplication.instance().setWindowIcon(icon)