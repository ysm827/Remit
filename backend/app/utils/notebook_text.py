"""Read notebook evidence without rendering or executing embedded HTML."""

from html.parser import HTMLParser


class _TextOnlyHTML(HTMLParser):
    def __init__(self):
        super().__init__(convert_charrefs=True)
        self.hidden = 0
        self.parts: list[str] = []

    def handle_starttag(self, tag, attrs):
        if tag in {"script", "style", "head"}:
            self.hidden += 1
        elif tag in {"br", "p", "div", "tr"} and not self.hidden:
            self.parts.append("\n")

    def handle_endtag(self, tag):
        if tag in {"script", "style", "head"}:
            self.hidden = max(0, self.hidden - 1)

    def handle_data(self, data):
        if not self.hidden:
            self.parts.append(data)


def notebook_output_text(output: dict) -> str:
    def join(value):
        return (
            "".join(str(part) for part in value)
            if isinstance(value, list)
            else str(value or "")
        )

    data = output.get("data") or {}
    text = output.get("text") or output.get("traceback") or data.get("text/plain")
    if text:
        return join(text)
    html = data.get("text/html")
    if html:
        parser = _TextOnlyHTML()
        parser.feed(join(html))
        parser.close()
        return "".join(parser.parts).strip()
    return ""
