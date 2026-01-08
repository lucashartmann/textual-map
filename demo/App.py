from textual.app import App, ComposeResult
from textual.widgets import Footer, Header
from textual.containers import Center
from textual_map import MapWidget


class TesteMapa(App):

    CSS = """
    MapWidget { 
        height: 37; 
        width: 100%;
        margin: 4;
    }
    """

    def compose(self) -> ComposeResult:
        yield Header()
        yield Center(MapWidget(address="Praça da Sé, São Paulo SP"))
        yield Footer()


if __name__ == "__main__":
    TesteMapa().run()
