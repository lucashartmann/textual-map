from textual.app import App, ComposeResult
from textual.widgets import Header, Footer
from .map_widget import MapWidget
import sys


class MapDemoApp(App):
    CSS = """
    MapWidget {
        height: 20;
    }
    """

    def __init__(self, address: str | None = None, **kwargs):
        super().__init__(**kwargs)
        self.address = address

    def compose(self) -> ComposeResult:
        yield Header()
        yield MapWidget(address=self.address)
        yield Footer()


if __name__ == "__main__":
    addr = None
    if len(sys.argv) > 1:
        addr = " ".join(sys.argv[1:])
    MapDemoApp(address=addr).run()
