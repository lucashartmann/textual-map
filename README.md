### textual-map

![Visual do Widget](/Example.png)
![Visual do Widget](/Example2.png)
![Visual do Widget](/Example3.png)

## Usage


```python
from textual.app import App
from textual_map import MapWidget
from textual_map.map_widget import Tipo

class TesteMapa(App):

    def compose(self):
        yield MapWidget(address="Praça da Sé, São Paulo SP")
        # yield MapWidget(address="Praça da Sé, São Paulo SP", zoom=2, tipo=Tipo.HALFCELL)


if __name__ == "__main__":
    TesteMapa().run()

```