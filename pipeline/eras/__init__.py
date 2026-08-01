"""Era Plugin 架构 — 动态路由，消除所有 if-era 硬编码分支"""
from pipeline.eras.base import BaseEra
from pipeline.eras.ancient import AncientEra
from pipeline.eras.literary import LiteraryEra

ERA_REGISTRY = {
    "ancient": AncientEra,
    "literary": LiteraryEra,
}

def get_era(book_config: dict, global_config: dict) -> BaseEra:
    name = book_config.get("era", "ancient")
    cls = ERA_REGISTRY.get(name, AncientEra)
    return cls(book_config, global_config)
