# -*- coding: utf-8 -*-
"""
QGIS Network Access Manager proxy detection helper.
Extracted into a standalone module with zero third-party dependencies (no requests)
to keep infrastructure and core importable in minimal environments.
"""


def get_qgis_proxy_dict():
    """Extracts proxy configuration from QgsNetworkAccessManager if active.
    Returns a dict suitable for requests ({"http": ..., "https": ...}) or None.
    """
    try:
        from qgis.core import QgsNetworkAccessManager
        from qgis.PyQt.QtNetwork import QNetworkProxy
        nam = QgsNetworkAccessManager.instance()
        if nam is not None:
            proxy = nam.fallbackProxySettings()
            if proxy.type() != QNetworkProxy.ProxyType.NoProxy if hasattr(QNetworkProxy, "ProxyType") else proxy.type() != 0:
                host = proxy.hostName()
                port = proxy.port()
                user = proxy.user()
                password = proxy.password()
                if host:
                    auth = f"{user}:{password}@" if user else ""
                    proxy_url = f"http://{auth}{host}:{port}"
                    return {"http": proxy_url, "https": proxy_url}
    except Exception:
        pass
    return None
