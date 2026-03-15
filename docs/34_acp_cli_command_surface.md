# ACP CLI v1 Command Surface

## Purpose
This document freezes the public ACP CLI v1 command surface.
It defines the commands that are part of the supported CLI shape for the current implementation phase.

## Client
- acp identity create
- acp identity show
- acp identity export
- acp identity verify
- acp discover get
- acp discover list
- acp discover well-known
- acp register put
- acp register update
- acp register show
- acp message send
- acp message capabilities
- acp agent run
- acp agent status
- acp transport list
- acp transport probe

## Relay
- acp relay run
- acp relay status
- acp relay health
- acp relay registry list
- acp relay registry show
- acp relay routes show
- acp relay ops stats
- acp relay ops failures

## Shared
- acp config show
- acp config validate
- acp ops logs
- acp ops metrics

## Change Rule
Any addition, removal, or rename to this command surface should be treated as an explicit CLI versioning decision.
