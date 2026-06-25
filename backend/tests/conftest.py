"""Pytest configuration: gate the slow (MCMC) integration test behind a flag."""

import pytest


def pytest_addoption(parser):
    parser.addoption(
        "--run-slow", action="store_true", default=False,
        help="run slow tests that fit real Bayesian models (needs bambi/pymc)",
    )


def pytest_configure(config):
    config.addinivalue_line("markers", "slow: marks tests that fit real models")


def pytest_collection_modifyitems(config, items):
    if config.getoption("--run-slow"):
        return
    skip = pytest.mark.skip(reason="needs --run-slow (fits a real Bayesian model)")
    for item in items:
        if "slow" in item.keywords:
            item.add_marker(skip)
