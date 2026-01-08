### textual-map

![Visual do Widget](/Example.png)
![Visual do Widget](/Example2.png)

## Usage


```python
from textual.app import App
from textual_map import MapWidget

class TesteMapa(App):

    CSS = """
    MapWidget { 
        height: 37; 
        width: 100%;
        margin: 4;
    }
    """

    def compose(self):
        yield MapWidget(address="Praça da Sé, São Paulo SP")


if __name__ == "__main__":
    TesteMapa().run()

```