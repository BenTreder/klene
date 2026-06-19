# Security Policy

Klene is a cleanup utility. That means safety issues deserve careful review because they can affect real user systems and data.

## Reporting A Safety Or Security Issue

If you find a vulnerability, unsafe cleanup path, confirmation bypass, or package removal issue, please report it privately through BenTreder.com first instead of opening a public issue.

- Contact route: BenTreder.com
- Include:
  - what happened
  - what version you tested
  - whether data deletion or package removal is involved
  - steps to reproduce if you can share them safely

## Scope

Please report issues such as:

- unsafe path handling
- cleanup actions that skip preview or confirmation
- destructive commands running unexpectedly
- privilege escalation problems
- command injection or shell safety issues

## Response Approach

Reports involving cleanup behavior will be treated with extra caution. Fixes should prefer the safer path even when it means being more conservative.
