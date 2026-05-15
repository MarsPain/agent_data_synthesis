# Architecture Explainers

This document collects detailed explanations for architecture and algorithm concepts used by the Agent Data Synthesis framework. Use it for concepts that need more teaching-oriented detail than [../DESIGN.md](../DESIGN.md), but should not become source-material notes like [../references/agent-data-synthesis-pdf-analysis.md](../references/agent-data-synthesis-pdf-analysis.md).

## How To Add An Explainer

Each explainer should answer:

- What the concept is.
- Why it matters for this framework.
- What components or contracts it implies.
- How it differs from simpler or adjacent approaches.
- How it maps to the current implementation plan.

Keep explainers concrete enough to guide design decisions. If an explainer changes a system contract, update the relevant canonical docs as well.

## AWM Environment Model

AWM, or Agent World Model, can be understood as an environment model that turns a natural-language application scenario into an executable, interactive, and verifiable simulated world.

It is not a text-only simulation where an LLM pretends that an environment exists. The important distinction is that the environment has real state and executable behavior. An Agent interacts with it through tools, receives observations, changes state, and can be evaluated by independent verification logic.

### Core Idea

The core idea is to build a code-backed world before generating training trajectories. The system first creates an environment, then exposes tools over that environment, then generates tasks that are feasible inside the environment, then records Agent trajectories, and finally verifies whether those trajectories actually satisfy the task.

In short:

```text
scenario -> state model -> tools/API -> task -> trajectory -> verifier
```

### What An AWM-Style Environment Contains

An AWM-style environment usually contains:

- **Domain scenario:** the application context, such as e-commerce, restaurant booking, travel planning, customer support, or inventory management.
- **State database:** structured state, often represented with SQLite or a similar database.
- **Business rules:** constraints and transitions that define valid behavior.
- **Tool/API layer:** controlled functions that the Agent can call instead of directly mutating state.
- **Observations:** structured results, errors, or state summaries returned after tool calls.
- **Verifiable tasks:** tasks whose success can be checked by program logic.

For an e-commerce environment, the state might include users, products, orders, carts, and inventory. Business rules might say that an order cannot be placed when inventory is insufficient, that inventory decreases after purchase, and that canceled orders restore inventory. Tools might include `search_products`, `add_to_cart`, `place_order`, and `check_order_status`.

### Example

```text
Scenario:
E-commerce platform.

State:
- users
- products
- orders
- inventory

Tools:
- search_product(query, max_price)
- check_inventory(product_id)
- place_order(user_id, product_id, quantity)
- check_order_status(order_id)

Task:
"Help the user buy an in-stock Bluetooth headset under 100."

Trajectory:
1. search_product("Bluetooth headset", max_price=100)
2. Observe candidate products.
3. check_inventory(product_id)
4. place_order(user_id, product_id, quantity=1)
5. Return a purchase confirmation.

Verifier:
- The selected product is a Bluetooth headset.
- The product price is <= 100.
- Inventory was available before purchase.
- The order exists for the correct user.
- Inventory decreased by the purchased quantity.
```

This differs from ordinary synthetic instruction data. A flat sample might say:

```text
User: Help me buy a Bluetooth headset.
Assistant: Done, I bought one for you.
```

That answer is not verifiable. In an AWM-style environment, "bought one" must correspond to a real state transition in the environment.

### Why It Matters For Agent Data Synthesis

Agent training data should teach procedural behavior: choosing tools, inspecting observations, reacting to errors, and completing tasks through stateful interaction. Text-only examples cannot reliably teach these skills because they do not expose the environment mechanics.

The AWM environment model gives the framework:

- **Grounding:** tasks are based on entities and rules that exist.
- **Executability:** tool calls can actually run.
- **Statefulness:** actions can change the world.
- **Reproducibility:** reset recipes or checkpoints can recreate the task.
- **Verification:** success can be checked against state and rules.
- **Transferability:** a standard tool interface can later be exposed through MCP-compatible servers.

### Mapping To This Repository

The current design adopts the AWM environment model without requiring full MCP infrastructure in the MVP.

MVP form:

- SQLite-backed environments.
- Python environment classes.
- Python callable tools with explicit schemas.
- Reset recipes and environment versions.
- Independent executable verifiers.
- JSONL samples with environment, tool, trajectory, verifier, quality, and lineage fields.

Later form:

- MCP-compatible environment and tool servers.
- Containerized environment execution.
- Reusable environment templates and cached base states.
- Cross-environment evaluation and transfer tests.

This staging matters. The first implementation should prove the environment and data contracts locally. MCP should be treated as an interoperability adapter after the core environment model is stable.

### Design Consequences

AWM implies several non-negotiable contracts:

- A generated task must be feasible in its environment.
- A tool must declare its input schema, return schema, side effects, and version.
- A trajectory must record enough observations to explain the final answer.
- A verifier must inspect environment state or tool results independently from the generator.
- A dataset sample must include environment and tool versions so it can be reproduced.

If a future design weakens these contracts, it stops being AWM-style and becomes ordinary text simulation.
