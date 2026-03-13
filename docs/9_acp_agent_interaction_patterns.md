
# ACP Agent Interaction Patterns (Draft)

## Overview

Agent Interaction Patterns describe common communication and coordination behaviors between autonomous agents using the Agent Communication Protocol (ACP).

These patterns help developers understand how ACP can be used to build real agent ecosystems.

ACP itself provides secure messaging primitives; interaction patterns describe how agents use those primitives to collaborate.

---

# 1. Task Delegation

## Description

One agent delegates a task to another agent.

Typical use cases:

- automation workflows
- service delegation
- distributed AI processing

## Flow

Agent A sends a task request to Agent B.

Possible outcomes:

- Agent B accepts the task
- Agent B rejects the task
- Agent B partially completes the task
- Agent B delegates the task further

## Example

Agent A → SEND (task_request) → Agent B  
Agent B → ACK → Agent A  
Agent B → SEND (task_result) → Agent A

---

# 2. Multi-Agent Task Distribution

## Description

A single agent distributes tasks to multiple agents simultaneously.

Example use cases:

- distributed computation
- inventory checks across suppliers
- multi-agent research tasks

## Flow

Agent A sends a multi-recipient SEND operation.

Each recipient may independently ACK or FAIL.

Partial completion may require COMPENSATE.

## Example

Agent A → SEND → Agents B, C, D  
Agent B → ACK  
Agent C → FAIL  
Agent D → ACK

Agent A → COMPENSATE (optional)

---

# 3. Event Broadcast

## Description

An agent broadcasts an event to multiple recipients.

Example use cases:

- status updates
- system alerts
- coordination signals

## Flow

Agent publishes event to a set of recipients.

Recipients process event asynchronously.

## Example

Agent A → SEND (event_notification) → Agents B, C, D

Recipients decide whether to respond or act.

---

# 4. Negotiation Pattern

## Description

Two or more agents negotiate an outcome.

Example use cases:

- pricing negotiation
- resource allocation
- contract negotiation

## Flow

Agents exchange messages iteratively until agreement or rejection.

## Example

Agent A → SEND (proposal) → Agent B  
Agent B → SEND (counter_offer) → Agent A  
Agent A → SEND (accept) → Agent B

---

# 5. Request / Response Pattern

## Description

An agent requests information or action from another agent and expects a reply.

## Flow

Agent A sends SEND message with correlation_id.

Agent B responds referencing in_reply_to.

## Example

Agent A → SEND (data_request) → Agent B  
Agent B → SEND (data_response, in_reply_to=message_id)

---

# 6. Workflow Coordination

## Description

Multiple agents collaborate to complete a workflow.

Example use cases:

- order processing
- insurance claims
- multi-step automation

## Flow

Agent orchestrator coordinates tasks among participants.

## Example

Coordinator → SEND (step1) → Agent B  
Agent B → ACK  
Coordinator → SEND (step2) → Agent C

---

# 7. Consensus or Voting

## Description

Agents collectively decide on an action.

Example use cases:

- distributed governance
- multi-agent decision systems

## Flow

Coordinator sends proposal.

Agents respond with vote.

Coordinator aggregates results.

## Example

Agent A → SEND (proposal) → Agents B, C, D  
Agents B,C,D → SEND (vote) → Agent A

---

# 8. Capability Discovery

## Description

Agents determine what another agent can support before initiating complex interactions.

## Flow

Agent A → CAPABILITIES → Agent B  
Agent B → CAPABILITIES response

---

# 9. Long-Running Task Tracking

## Description

Tasks may run asynchronously for extended periods.

Agents exchange progress updates.

## Example

Agent A → SEND (task_request) → Agent B  
Agent B → ACK  
Agent B → SEND (task_progress) → Agent A  
Agent B → SEND (task_complete) → Agent A

---

# 10. Failure and Compensation

## Description

If a multi-agent operation fails partially, the initiating agent may send a COMPENSATE message.

## Example

Agent A → SEND (reserve_inventory) → Agents B, C

Agent B → ACK  
Agent C → FAIL

Agent A → COMPENSATE (cancel reservation) → Agent B

---

# Design Goal

ACP interaction patterns provide guidance for building collaborative agent systems without embedding workflow logic directly in the protocol.

Agents remain autonomous while using ACP messaging primitives for coordination.
