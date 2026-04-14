# AgentSentinel — Safety controls for AI agents
# Copyright (c) 2026 Leland E. Doss. All rights reserved.
# Licensed under the Business Source License 1.1
# See LICENSE.md for details

"""Framework integrations for AgentSentinel.

Optional modules — import only if the matching framework is installed.

.. code-block:: python

    # LangChain (requires langchain installed)
    from agentsentinel.integrations.langchain import protect_langchain_agent

    # AutoGen (requires pyautogen / autogen-agentchat installed)
    from agentsentinel.integrations.autogen import AutoGenGuard

    # CrewAI (requires crewai installed)
    from agentsentinel.integrations.crewai import CrewAIGuard, protect_crew

    # LlamaIndex (requires llama-index installed)
    from agentsentinel.integrations.llamaindex import LlamaIndexGuard, protect_agent

    # OpenAI Assistants API (requires openai installed)
    from agentsentinel.integrations.openai_assistants import OpenAIAssistantsGuard, protect_function_map

    # Anthropic Claude Tools (requires anthropic installed)
    from agentsentinel.integrations.anthropic_tools import AnthropicToolsGuard, protect_tool_handlers
"""
