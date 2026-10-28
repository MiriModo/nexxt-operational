"""Pagina de demo (M6-T2): statică, autonomă, cu toate cazurile și metricile."""
from __future__ import annotations

import json
from html.parser import HTMLParser

import pytest

from retailagent.demo import build_html, main
from retailagent.pipeline import run_full


class Audit(HTMLParser):
    def __init__(self):
        super().__init__()
        self.scripts_externe, self.stylesheets, self.title, self.data_json, self._in = [], [], "", None, None

    def handle_starttag(self, tag, attrs):
        a = dict(attrs)
        if tag == "script" and a.get("src"):
            self.scripts_externe.append(a["src"])
        if tag == "link" and a.get("rel") == "stylesheet":
            self.stylesheets.append(a.get("href"))
        if tag == "script" and a.get("id") == "data":
            self._in = "data"
        if tag == "title":
            self._in = "title"

    def handle_data(self, data):
        if self._in == "data":
            self.data_json = (self.data_json or "") + data
        elif self._in == "title":
            self.title += data

    def handle_endtag(self, tag):
        self._in = None


@pytest.fixture(scope="module")
def html(pipeline, tmp_path_factory):
    full = run_full(pipeline["dir"], tmp_path_factory.mktemp("out"))
    gt = json.loads((pipeline["dir"] / "ground_truth.json").read_text(encoding="utf-8"))
    return build_html(full, gt)


def test_pagina_e_autonoma_si_mica(html):
    p = Audit()
    p.feed(html)
    assert p.scripts_externe == [] and p.stylesheets == []
    assert "http://" not in html.replace("http://www.w3.org", "") and "https://" not in html
    assert len(html.encode("utf-8")) < 5 * 1024 * 1024
    assert p.title.strip()
    assert html.lstrip().lower().startswith("<!doctype html>")


def test_datele_sunt_incorporate(html, pipeline):
    p = Audit()
    p.feed(html)
    data = json.loads(p.data_json)
    assert {"metrici", "cazuri"} <= set(data)
    assert len(data["cazuri"]) == len(pipeline["cases"])
    c = data["cazuri"][0]
    assert {"case", "check", "offer", "rec"} <= set(c)
    assert "cifra_vedeta" in data["metrici"]
    assert "</script" not in p.data_json


def test_elementele_ui(html):
    for s in ("Aprobă", "Modifică", "Respinge", "retailagent.approve", "Verificări", "Retenție", "Recomandare", "Semnale",
              "P1", "P2", "P3", "Cifra-vedetă", "interogări"):
        assert s in html, s


def test_cli_scrie_demo_html(pipeline, tmp_path):
    out = tmp_path / "out"
    main(["--data-dir", str(pipeline["dir"]), "--out-dir", str(out)])
    assert (out / "demo.html").exists() and (out / "demo.html").stat().st_size > 50_000
