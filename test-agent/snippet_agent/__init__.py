from . import tracing

tracing.setup()  # before the agent is built, so adk web's runs are traced

from . import agent  # noqa: E402
