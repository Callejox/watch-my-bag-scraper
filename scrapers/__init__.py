"""Módulo de scrapers para Chrono24 y Vestiaire Collective."""

from .base_scraper import BaseScraper
from .scraper_chrono import Chrono24Scraper
from .scraper_vestiaire import VestiaireScraper

__all__ = ["BaseScraper", "Chrono24Scraper", "VestiaireScraper"]
