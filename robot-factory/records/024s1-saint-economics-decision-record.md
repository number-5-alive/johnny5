# SAINT decision record: 024s1-saint-economics

> This record states agreement reached in a SAINT session, not verification. Consensus here is agreement only: nothing in it was run, tested or checked, and it carries no verified stamp and no Grasshopper stamp.

*Assembled by bin/scribe.py on 2026-11-01T15:25:20-06:00 from `sessions/024s1-saint-economics/`. The scribe holds no vote.*

## Header

- Agenda: The next economic system in the world of automation (AGENDA line)
- Ruleset: `saint` (budget section `saint`, word-only: yes)
- Status: **round_cap**: round cap 3 reached. Rounds allowed 3, rounds held 3.

### Seats and capacities

| Seat | Capacity | Vote |
|---|---|---|
| `claude_code` | proposer | votes |
| `codex` | challenger | votes |
| `claude_code` | chair | votes |
| `qwen_local` | scribe: Johnny (qwen_local), bin/scribe.py through seats/qwen_local.sh (local) | no vote |

### Commission

From `sessions/024s1-saint-economics/brief.md`, verbatim:

```markdown
RULESET: saint
SEAT proposer: claude_code
SEAT challenger: codex
SEAT chair: claude_code
AGENDA: The next economic system in the world of automation
SCRIBE: johnny
LABEL: POSITION
FORBID: em-dash

Commissioned by Dan Page, 2026-11-01. This is SAINT's first live
session. The question before the room:

As automation and AI absorb more of the labor the economy
currently pays people to do, what economic system should
follow? Not what is merely likely, but what arrangement best
serves human flourishing, stated as a position with its core
mechanisms named: who owns the productive system, how its
output is distributed, what role work plays in a person's life
and standing, and how a society gets from here to there.

The commissioner's own starting points are on the table to be
examined, not assumed: a national project to build the
automated capacity and train people alongside it; a basic
income as the distribution floor; equal one-stake ownership of
the productive system by every citizen, with operational
control delegated to a larger AI; and the open question of
whether any of this requires abandoning capitalism or is
instead its next form.

Ground rules for the room:
- Take a position. A survey of options is not a position.
- Mechanisms over slogans: for each element, say how it works,
  who decides, and what could break it.
- The position should run roughly 600 to 900 words.
- Plain language throughout. This record may be published.
```

## Positions by round (verbatim)

### Round 0: opening

#### proposer (`claude_code`)

```markdown
POSITION

The economy that should follow mass automation is a market economy with universal ownership: private firms keep competing to make things, but the returns from automated capital flow to every citizen through an equal, permanent stake in a national fund. Markets decide what gets made. Citizens own a large and growing share of what does the making. Humans govern the fund, and AI serves as its instrument, not its master. This is not the end of capitalism but a correction to its central flaw in an automated age: when capital does the work, whoever owns capital owns the economy, so ownership must be spread as widely as voting.

**1. Ownership: a citizens' fund, not a state monopoly**

A national fund, modeled on Alaska's Permanent Fund and Norway's sovereign fund but far larger, accumulates equity in the productive economy. It grows through three channels:
- a small annual equity levy on large firms, paid in shares rather than cash, so the fund's ownership rises without draining operating capital;
- royalties on public resources that automation depends on, such as spectrum, land, energy rights, and publicly funded research;
- retained returns.

Every citizen holds exactly one stake from birth. It cannot be sold, pledged, or inherited, which keeps it from being concentrated again. The commissioner's equal one-stake principle is right, and it is the heart of this position.

The fund is a diversified minority owner. It does not run companies. Private and cooperative firms still start, compete, fail, and are replaced. That keeps the discovery process of markets, which central ownership has repeatedly destroyed.

What could break it: political raids on the fund for short-term spending, capital flight to escape the levy, and slow ossification into a giant passive owner that props up incumbents. The defenses are a constitutional or supermajority lock on the principal, levy coordination with trading partners plus border adjustments, and a mandate that requires the fund to hold broad indexes rather than pick winners.

**2. Distribution: a floor, then a dividend**

Distribution has two layers. The first is a basic income floor, funded at first from general taxation, set at a level that covers housing, food, and health in modest terms. It begins small and is indexed upward as productivity rises. The second is the fund dividend, paid equally to every stakeholder. Over decades, as the fund grows, the dividend should overtake the floor as the main source of non-wage income.

The reason for two layers: the floor is a promise of security that should not depend on markets. The dividend is a share of prosperity that should. Keeping them separate prevents a bad market year from threatening anyone's rent.

Public services (health, education, transit) remain funded directly. Cash does not replace them, because some goods are better supplied in common.

What could break it: inflation in scarce goods, especially housing, which would absorb the payments. So the income program has to come with aggressive building reform. Cash without supply just raises rents.

**3. Work: decoupled from survival, not from standing**

Work should stop being the price of staying alive. It should not stop mattering. People need to be needed, and a society that tells most of its members they are surplus will fracture regardless of how well they are fed.

So the system rewards contribution broadly defined. Paid work continues wherever humans are wanted or better. Care, teaching, civic service, repair, and craft get public recognition and modest supplements through a national service structure that people can enter and leave freely. Standing should come from what you give, and the system should make giving easy to start.

**4. Governance: humans decide, AI advises and executes**

On this point I disagree with the commissioner. Operational control of the productive system should not be delegated to a larger AI. Delegation would separate ownership from control almost completely. A citizen whose stake is managed by a system they cannot question owns a receipt, not a share. It also creates a single point of failure, both technical and political: whoever shapes that AI's objectives effectively rules.

Instead, an elected and audited board governs the fund under published rules. AI systems run analysis, compliance, and routine execution under human sign-off, with open logs and the right of citizens and auditors to challenge decisions. Use AI to make accountability cheaper, not to replace it.

**5. Transition: build, train, and phase in**

The commissioner's national project belongs here, aimed narrowly. Government should build the public foundations that markets underprovide, namely energy, compute capacity, data infrastructure, and training, and should take equity stakes in return for public money that de-risks private automation. Workers displaced by automation get paid retraining and a guaranteed place in the service structure, so no one falls between jobs.

Sequence over roughly twenty years:
1. Create the fund and stakes, and set the levy low.
2. Start a small floor and pair it with housing reform.
3. Raise the levy and royalties on a published schedule tied to measured labor displacement, so the system scales with the problem rather than ahead of it.

**On capitalism**

Keep competition, prices, private enterprise, and the freedom to build. Change who owns the returns. That is capitalism's next form, and the only form likely to survive automation with democratic consent.
```

### Round 1

#### challenger (`codex`)

```markdown
P1: The position assumes rising productivity means a growing fund dividend, but an annual share levy can dilute existing owners without creating new productive value; it gives no rule for sizing the levy or preventing firms from shifting investment, profits, or incorporation abroad.

P2: The basic income is funded “at first” by general taxation, but the position never identifies a durable revenue source or explains how it competes with the fund dividend as that dividend grows. The proposed labor-displacement trigger also leaves unclear how displacement is measured and who sets the schedule.

P3: A diversified minority stake does not by itself give citizens meaningful ownership or influence over firms. The position rejects AI control on accountability grounds but gives citizens no clear route to shape the elected fund board’s choices, challenge its votes, or remove directors.

P4: The service structure risks recreating a status hierarchy around officially recognized contribution. The position says standing should come from giving, but does not explain how people who cannot serve, choose private pursuits, or do unrecognized care work retain equal standing without supplements.

P5: The claim that this is “the only form likely to survive automation with democratic consent” is unsupported. The position does not compare its model with alternatives such as worker ownership, broader public ownership, or a basic-income system financed by taxes rather than a national equity fund.
```

#### chair (`claude_code`)

```markdown
=== MERGE RECORD ===
P1: ACCEPT - A share levy transfers ownership rather than creating value, so the position needs an explicit sizing rule and concrete anti-avoidance measures, and should say plainly that dividend growth depends on automated profits, not on the levy itself.
P2: ACCEPT - The floor needs a named, durable revenue base and a stated relationship to the dividend, and the displacement trigger needs a defined measure and an independent body to apply it.
P3: ACCEPT - Rejecting AI control on accountability grounds obliges the position to give citizens real powers over the human board, including direct election, recall, and published voting.
P4: ACCEPT - Tying standing to recognized service risks a new hierarchy, so the floor and stake must be unconditional and equal standing must not depend on supplements or official recognition.
P5: ACCEPT - The "only form" claim is asserted rather than argued, so the position should compare itself briefly with the main alternatives and state its claim at the strength the reasoning supports.
=== ARTIFACT ===
POSITION

The economy that should follow mass automation is a market economy with universal ownership: private firms keep competing to make things, but the returns from automated capital flow to every citizen through an equal, permanent stake in a national fund. Markets decide what gets made. Citizens own a large and growing share of what does the making. Humans govern the fund, and AI serves as its instrument, not its master. When capital does the work, whoever owns capital owns the economy, so ownership must be spread as widely as voting.

**1. Ownership: a citizens' fund, not a state monopoly**

A national fund, modeled on Alaska's Permanent Fund and Norway's sovereign fund but far larger, accumulates equity in the productive economy through three channels: an annual equity levy on large firms, paid in newly issued shares; royalties on public resources automation depends on, such as spectrum, land, energy rights, and publicly funded research; and retained returns.

The levy moves ownership; it does not create wealth. Existing shareholders are diluted, and the dividend grows only if automated firms are actually profitable. So the levy is sized by rule: it starts at 0.5 percent of shares per year for firms above a size threshold, rises only on the published schedule in section 5, and is capped so the fund never exceeds a set share (for example 30 percent) of any one firm. Avoidance is met by applying the levy by where sales and assets are, not where a firm is incorporated, by coordinating with trading partners, and by border adjustments on firms that relocate to escape it.

Every citizen holds exactly one stake from birth. It cannot be sold, pledged, or inherited. The fund holds broad indexes and does not run companies; private and cooperative firms still start, compete, fail, and are replaced. A constitutional or supermajority lock protects the principal from political raids.

**2. Distribution: a floor, then a dividend**

The first layer is a basic income floor covering housing, food, and health in modest terms. It is paid for by dedicated taxes on land value and consumption, chosen because land cannot leave and consumption is hard to hide. The second layer is the fund dividend, paid equally to every stakeholder.

The two do not compete. The floor is a fixed promise; the dividend is a variable share of prosperity. As the dividend grows, a published formula lets a portion of fund returns replace the land and consumption taxes, but the floor's legal guarantee never depends on market performance. A bad market year cannot threaten anyone's rent.

Public services such as health, education, and transit stay directly funded. Cash comes paired with aggressive building reform, because cash without supply just raises rents.

**3. Work: decoupled from survival and from standing**

Work should stop being the price of staying alive. People still need to be needed, and the system should make contribution easy: paid work continues wherever humans are wanted, and a voluntary national service structure offers care, teaching, civic, repair, and craft roles with modest supplements.

But standing must not be rationed by official recognition. The floor and the stake are unconditional and identical for the person who serves, the person who cannot, the person caring for a parent unpaid, and the person pursuing private work. Supplements reward chosen effort; they never decide who counts. Unpaid carers may claim the supplement by simple self-declaration, without needing to prove their care in a bureaucracy.

**4. Governance: humans decide, AI advises and executes**

On this point I disagree with the commissioner. Delegating operational control to a larger AI would separate ownership from control almost completely and would create a single point of failure: whoever shapes that AI's objectives effectively rules.

Instead, the fund is run by a board whose members are directly elected by stakeholders on staggered terms. Citizens get real levers: the board publishes every shareholder vote and its reasons; a petition by a set share of stakeholders forces a recall election for any director; stakeholders vote periodically on binding voting guidelines for issues like pay and environmental risk; and an independent auditor and ombudsman hear challenges. AI systems run analysis, compliance, and routine execution under human sign-off, with open logs. AI makes accountability cheaper; it does not replace it.

**5. Transition: build, train, and phase in**

Government builds the foundations markets underprovide (energy, compute, data infrastructure, training) and takes equity stakes in return for public money that de-risks private automation. Displaced workers get paid retraining and a guaranteed service place.

Over roughly twenty years: create the fund and stakes with the levy at its floor; start a small basic income paired with housing reform; then raise the levy and royalties on a published schedule. That schedule is set by an independent statistics office, insulated like a central bank, using a defined displacement index: the decline in labor's share of national income and in hours worked per adult. Parliament can slow the schedule only by supermajority.

**On capitalism and the alternatives**

Worker ownership spreads control but leaves out people outside the firm, and the automated firms with few workers are exactly where returns will concentrate. Broad public ownership has a poor record at innovation. Tax-funded basic income alone can work, but gives citizens no compounding claim on future output and must be refought every budget. This model keeps competition, prices, and private enterprise while changing who owns the returns, and welcomes cooperatives within it. It is capitalism's next form, and in this room's judgment the arrangement most likely to keep democratic consent through automation, though not the only one that could.
```

### Round 2

Standings in front of the seats: `sessions/024s1-saint-economics/r2-standings.md` (record, not opinion; no vote).

#### challenger (`codex`)

```markdown
P1: The basic-income promise remains financially underspecified: land and consumption taxes may not raise enough to cover housing, food, and health at a meaningful level, and the text gives no fallback if revenues fall short or the fund dividend cannot replace taxes without weakening the floor.
```

#### chair (`claude_code`)

```markdown
=== MERGE RECORD ===
P1: ACCEPT - The floor is the system's central promise of security, so the position must say how its level is set against real revenue, what backstop applies if dedicated taxes fall short, and the test the fund must pass before it replaces those taxes.
=== ARTIFACT ===
POSITION

The economy that should follow mass automation is a market economy with universal ownership: private firms keep competing to make things, but the returns from automated capital flow to every citizen through an equal, permanent stake in a national fund. Markets decide what gets made. Citizens own a large and growing share of what does the making. Humans govern the fund, and AI serves as its instrument, not its master. When capital does the work, whoever owns capital owns the economy, so ownership must be spread as widely as voting.

**1. Ownership: a citizens' fund, not a state monopoly**

A national fund, modeled on Alaska's Permanent Fund and Norway's sovereign fund but far larger, accumulates equity in the productive economy through three channels: an annual equity levy on large firms, paid in newly issued shares; royalties on public resources automation depends on, such as spectrum, land, energy rights, and publicly funded research; and retained returns.

The levy moves ownership; it does not create wealth. Existing shareholders are diluted, and the dividend grows only if automated firms are actually profitable. So the levy is sized by rule: it starts at 0.5 percent of shares per year for firms above a size threshold, rises only on the published schedule in section 5, and is capped so the fund never exceeds a set share (for example 30 percent) of any one firm. Avoidance is met by applying the levy by where sales and assets are, not where a firm is incorporated, by coordinating with trading partners, and by border adjustments on firms that relocate to escape it.

Every citizen holds exactly one stake from birth. It cannot be sold, pledged, or inherited. The fund holds broad indexes and does not run companies. A constitutional or supermajority lock protects the principal from political raids.

**2. Distribution: a floor, then a dividend**

The first layer is a basic income floor covering housing, food, and health in modest terms. Its primary funding is dedicated taxes on land value and consumption, chosen because land cannot leave and consumption is hard to hide. These may not be enough on their own, so the floor is built to hold even when they fall short:

- The floor starts at the level dedicated revenue can actually sustain and rises toward its full target only as that revenue, measured over several years, supports it. It does not promise more than it can pay.
- If dedicated revenue falls short in any year, a statutory backstop draws automatically on general revenue, including income and wealth taxes, before any other new spending. The floor has first claim on the budget.
- A reserve, built from surplus years, smooths downturns so a recession does not force a cut.

The second layer is the fund dividend, paid equally to every stakeholder. The two do not compete. The floor is a fixed legal promise; the dividend is a variable share of prosperity. Fund returns may replace the land and consumption taxes only after they have covered the floor's cost with a safety margin for a sustained period, for example five years, and the replacement is reversed automatically if that test later fails. The dividend never comes before the floor.

Public services such as health, education, and transit stay directly funded. Cash comes paired with aggressive building reform, because cash without supply just raises rents.

**3. Work: decoupled from survival and from standing**

Work should stop being the price of staying alive. People still need to be needed, so the system makes contribution easy: paid work continues wherever humans are wanted, and a voluntary national service structure offers care, teaching, civic, repair, and craft roles with modest supplements.

Standing must not be rationed by official recognition. The floor and the stake are unconditional and identical for the person who serves, the person who cannot, the person caring for a parent unpaid, and the person pursuing private work. Supplements reward chosen effort; they never decide who counts. Unpaid carers may claim the supplement by simple self-declaration.

**4. Governance: humans decide, AI advises and executes**

On this point I disagree with the commissioner. Delegating operational control to a larger AI would separate ownership from control and create a single point of failure: whoever shapes that AI's objectives effectively rules.

Instead, the fund is run by a board directly elected by stakeholders on staggered terms. The board publishes every shareholder vote and its reasons; a petition by a set share of stakeholders forces a recall election for any director; stakeholders vote periodically on binding voting guidelines for issues like pay and environmental risk; and an independent auditor and ombudsman hear challenges. AI runs analysis, compliance, and routine execution under human sign-off, with open logs.

**5. Transition: build, train, and phase in**

Government builds the foundations markets underprovide (energy, compute, data infrastructure, training) and takes equity stakes in return for public money that de-risks private automation. Displaced workers get paid retraining and a guaranteed service place.

Over roughly twenty years: create the fund and stakes with the levy at its floor; start a small basic income paired with housing reform; then raise the levy and royalties on a published schedule. That schedule is set by an independent statistics office, insulated like a central bank, using a defined displacement index: the decline in labor's share of national income and in hours worked per adult. Parliament can slow the schedule only by supermajority.

**On capitalism and the alternatives**

Worker ownership leaves out people outside the firm, and automated firms with few workers are exactly where returns will concentrate. Broad public ownership has a poor record at innovation. Tax-funded basic income alone can work, but gives citizens no compounding claim on future output and must be refought every budget. This model keeps competition, prices, and private enterprise while changing who owns the returns, and welcomes cooperatives within it. It is capitalism's next form, and in this room's judgment the arrangement most likely to keep democratic consent through automation, though not the only one that could.
```

### Round 3

Standings in front of the seats: `sessions/024s1-saint-economics/r3-standings.md` (record, not opinion; no vote).

#### challenger (`codex`)

```markdown
P1: “The floor does not compete” with the dividend, yet the proposal makes the dividend’s rise contingent on automated firms being profitable while relying on taxes and a general-revenue backstop for the floor; it does not explain how that backstop remains affordable if automation also erodes wage and income-tax bases.
```

#### chair (`claude_code`)

```markdown
=== MERGE RECORD ===
P1: ACCEPT - If automation shrinks wages, a backstop that leans on income taxes weakens just when it is needed, so the floor's backstop must be tied to the capital side of the economy that automation enlarges, and the claim that floor and dividend "do not compete" must be stated more honestly.
=== ARTIFACT ===
POSITION

The economy that should follow mass automation is a market economy with universal ownership. Private firms keep competing to make things, but the returns from automated capital flow to every citizen through an equal, permanent stake in a national fund. Markets decide what gets made. Citizens own a large and growing share of what does the making. Humans govern the fund, and AI serves as its instrument, not its master. When capital does the work, whoever owns capital owns the economy, so ownership must be spread as widely as voting.

**1. Ownership: a citizens' fund, not a state monopoly**

A national fund, modeled on Alaska's Permanent Fund and Norway's sovereign fund but far larger, builds equity in the productive economy through three channels:
- an annual equity levy on large firms, paid in newly issued shares;
- royalties on public resources automation depends on, such as spectrum, land, energy rights, and publicly funded research;
- retained returns.

The levy moves ownership; it does not create wealth. Existing shareholders are diluted, and the dividend grows only if automated firms are actually profitable. So the levy is sized by rule. It starts at 0.5 percent of shares per year for firms above a size threshold, rises only on the published schedule in section 5, and is capped so the fund never exceeds a set share (for example 30 percent) of any one firm. Avoidance is met in three ways: the levy applies by where sales and assets are, not where a firm is incorporated; it is coordinated with trading partners; and border adjustments apply to firms that relocate to escape it.

Every citizen holds exactly one stake from birth. It cannot be sold, pledged, or inherited. The fund holds broad indexes and does not run companies. A constitutional or supermajority lock protects the principal from political raids.

**2. Distribution: a floor, then a dividend**

The first layer is a basic income floor covering housing, food, and health in modest terms. Its primary funding is dedicated taxes on land value and consumption, chosen because land cannot leave and consumption is hard to hide.

Automation threatens the usual backstop. If wages fall, income taxes fall with them, so a floor that leans on taxing wages would weaken exactly when it is most needed. The floor is therefore anchored to the side of the economy that automation enlarges:
- The floor starts at the level dedicated revenue can actually sustain and rises toward its full target only as that revenue, measured over several years, supports it. It does not promise more than it can pay.
- If dedicated revenue falls short in any year, a statutory backstop draws first on taxes on capital income, corporate profits, and large fortunes. As labor's share of income falls, capital's share rises, so these bases grow with the problem rather than shrink with it. The backstop draws on wage taxes only last.
- A reserve, built from surplus years, smooths downturns so a recession does not force a cut.
- As a final guarantee, if both dedicated taxes and the capital backstop fall short, the floor has first claim on fund returns before any dividend is paid.

The floor and the dividend are not fully independent: both ultimately depend on automated production being profitable and taxable. What the design ensures is the order of claims. The floor is a fixed legal promise paid first; the dividend is a variable share of whatever remains. Fund returns may replace the land and consumption taxes only after they have covered the floor's cost with a safety margin for a sustained period, for example five years, and that replacement reverses automatically if the test later fails.

Public services such as health, education, and transit stay directly funded. Cash comes paired with aggressive building reform, because cash without supply just raises rents.

**3. Work: decoupled from survival and from standing**

Work should stop being the price of staying alive. People still need to be needed, so the system makes contribution easy. Paid work continues wherever humans are wanted, and a voluntary national service structure offers care, teaching, civic, repair, and craft roles with modest supplements.

Standing must not be rationed by official recognition. The floor and the stake are unconditional and identical for four kinds of person: the one who serves, the one who cannot, the one caring for a parent unpaid, and the one pursuing private work. Supplements reward chosen effort; they never decide who counts. Unpaid carers may claim the supplement by simple self-declaration.

**4. Governance: humans decide, AI advises and executes**

On this point I disagree with the commissioner. Delegating operational control to a larger AI would separate ownership from control and create a single point of failure: whoever shapes that AI's objectives effectively rules.

Instead, the fund is run by a board directly elected by stakeholders on staggered terms, with four checks on it:
- The board publishes every shareholder vote and its reasons.
- A petition by a set share of stakeholders forces a recall election for any director.
- Stakeholders vote periodically on binding voting guidelines for issues like pay and environmental risk.
- An independent auditor and ombudsman hear challenges.

AI runs analysis, compliance, and routine execution under human sign-off, with open logs.

**5. Transition: build, train, and phase in**

Government builds the foundations markets underprovide: energy, compute, data infrastructure, and training. It takes equity stakes in return for public money that de-risks private automation. Displaced workers get paid retraining and a guaranteed service place.

The phase-in runs over roughly twenty years:
1. Create the fund and stakes, with the levy at its starting rate.
2. Start a small basic income paired with housing reform, with the capital-side backstop in law from the start.
3. Raise the levy and royalties on a published schedule.

That schedule is set by an independent statistics office, insulated like a central bank, using a defined displacement index: the decline in labor's share of national income and in hours worked per adult. Parliament can slow the schedule only by supermajority.

**On capitalism and the alternatives**

Worker ownership leaves out people outside the firm, and automated firms with few workers are exactly where returns will concentrate. Broad public ownership has a poor record at innovation. Tax-funded basic income alone can work, but gives citizens no compounding claim on future output and must be refought every budget.

This model keeps competition, prices, and private enterprise while changing who owns the returns, and it welcomes cooperatives within it. It is capitalism's next form. In this room's judgment it is the arrangement most likely to keep democratic consent through automation, though not the only one that could.
```

## Agreements (accepted by the chair)

- Round 1 P1: The position assumes rising productivity means a growing fund dividend, but an annual share levy can dilute existing owners without creating new productive value; it gives no rule for sizing the levy or preventing firms from shifting investment, profits, or incorporation abroad.  
  Accepted: A share levy transfers ownership rather than creating value, so the position needs an explicit sizing rule and concrete anti-avoidance measures, and should say plainly that dividend growth depends on automated profits, not on the levy itself.
- Round 1 P2: The basic income is funded “at first” by general taxation, but the position never identifies a durable revenue source or explains how it competes with the fund dividend as that dividend grows. The proposed labor-displacement trigger also leaves unclear how displacement is measured and who sets the schedule.  
  Accepted: The floor needs a named, durable revenue base and a stated relationship to the dividend, and the displacement trigger needs a defined measure and an independent body to apply it.
- Round 1 P3: A diversified minority stake does not by itself give citizens meaningful ownership or influence over firms. The position rejects AI control on accountability grounds but gives citizens no clear route to shape the elected fund board’s choices, challenge its votes, or remove directors.  
  Accepted: Rejecting AI control on accountability grounds obliges the position to give citizens real powers over the human board, including direct election, recall, and published voting.
- Round 1 P4: The service structure risks recreating a status hierarchy around officially recognized contribution. The position says standing should come from giving, but does not explain how people who cannot serve, choose private pursuits, or do unrecognized care work retain equal standing without supplements.  
  Accepted: Tying standing to recognized service risks a new hierarchy, so the floor and stake must be unconditional and equal standing must not depend on supplements or official recognition.
- Round 1 P5: The claim that this is “the only form likely to survive automation with democratic consent” is unsupported. The position does not compare its model with alternatives such as worker ownership, broader public ownership, or a basic-income system financed by taxes rather than a national equity fund.  
  Accepted: The "only form" claim is asserted rather than argued, so the position should compare itself briefly with the main alternatives and state its claim at the strength the reasoning supports.
- Round 2 P1: The basic-income promise remains financially underspecified: land and consumption taxes may not raise enough to cover housing, food, and health at a meaningful level, and the text gives no fallback if revenues fall short or the fund dividend cannot replace taxes without weakening the floor.  
  Accepted: The floor is the system's central promise of security, so the position must say how its level is set against real revenue, what backstop applies if dedicated taxes fall short, and the test the fund must pass before it replaces those taxes.
- Round 3 P1: “The floor does not compete” with the dividend, yet the proposal makes the dividend’s rise contingent on automated firms being profitable while relying on taxes and a general-revenue backstop for the floor; it does not explain how that backstop remains affordable if automation also erodes wage and income-tax bases.  
  Accepted: If automation shrinks wages, a backstop that leans on income taxes weakens just when it is needed, so the floor's backstop must be tied to the capital side of the economy that automation enlarges, and the claim that floor and dividend "do not compete" must be stated more honestly.

## Disagreements (rejected by the chair)

None.

## Dissent (preserved)

Objections the chair rejected, in the challenger's own words. They stand in the record beside the synthesis; agreement in the room does not erase them.

No dissent on record: the chair rejected no objection.

## Chair's synthesis

The chair's last restated position, `r3-chair-v4.md`, verbatim. It is agreement reached in this room, not verification.

```markdown
POSITION

The economy that should follow mass automation is a market economy with universal ownership. Private firms keep competing to make things, but the returns from automated capital flow to every citizen through an equal, permanent stake in a national fund. Markets decide what gets made. Citizens own a large and growing share of what does the making. Humans govern the fund, and AI serves as its instrument, not its master. When capital does the work, whoever owns capital owns the economy, so ownership must be spread as widely as voting.

**1. Ownership: a citizens' fund, not a state monopoly**

A national fund, modeled on Alaska's Permanent Fund and Norway's sovereign fund but far larger, builds equity in the productive economy through three channels:
- an annual equity levy on large firms, paid in newly issued shares;
- royalties on public resources automation depends on, such as spectrum, land, energy rights, and publicly funded research;
- retained returns.

The levy moves ownership; it does not create wealth. Existing shareholders are diluted, and the dividend grows only if automated firms are actually profitable. So the levy is sized by rule. It starts at 0.5 percent of shares per year for firms above a size threshold, rises only on the published schedule in section 5, and is capped so the fund never exceeds a set share (for example 30 percent) of any one firm. Avoidance is met in three ways: the levy applies by where sales and assets are, not where a firm is incorporated; it is coordinated with trading partners; and border adjustments apply to firms that relocate to escape it.

Every citizen holds exactly one stake from birth. It cannot be sold, pledged, or inherited. The fund holds broad indexes and does not run companies. A constitutional or supermajority lock protects the principal from political raids.

**2. Distribution: a floor, then a dividend**

The first layer is a basic income floor covering housing, food, and health in modest terms. Its primary funding is dedicated taxes on land value and consumption, chosen because land cannot leave and consumption is hard to hide.

Automation threatens the usual backstop. If wages fall, income taxes fall with them, so a floor that leans on taxing wages would weaken exactly when it is most needed. The floor is therefore anchored to the side of the economy that automation enlarges:
- The floor starts at the level dedicated revenue can actually sustain and rises toward its full target only as that revenue, measured over several years, supports it. It does not promise more than it can pay.
- If dedicated revenue falls short in any year, a statutory backstop draws first on taxes on capital income, corporate profits, and large fortunes. As labor's share of income falls, capital's share rises, so these bases grow with the problem rather than shrink with it. The backstop draws on wage taxes only last.
- A reserve, built from surplus years, smooths downturns so a recession does not force a cut.
- As a final guarantee, if both dedicated taxes and the capital backstop fall short, the floor has first claim on fund returns before any dividend is paid.

The floor and the dividend are not fully independent: both ultimately depend on automated production being profitable and taxable. What the design ensures is the order of claims. The floor is a fixed legal promise paid first; the dividend is a variable share of whatever remains. Fund returns may replace the land and consumption taxes only after they have covered the floor's cost with a safety margin for a sustained period, for example five years, and that replacement reverses automatically if the test later fails.

Public services such as health, education, and transit stay directly funded. Cash comes paired with aggressive building reform, because cash without supply just raises rents.

**3. Work: decoupled from survival and from standing**

Work should stop being the price of staying alive. People still need to be needed, so the system makes contribution easy. Paid work continues wherever humans are wanted, and a voluntary national service structure offers care, teaching, civic, repair, and craft roles with modest supplements.

Standing must not be rationed by official recognition. The floor and the stake are unconditional and identical for four kinds of person: the one who serves, the one who cannot, the one caring for a parent unpaid, and the one pursuing private work. Supplements reward chosen effort; they never decide who counts. Unpaid carers may claim the supplement by simple self-declaration.

**4. Governance: humans decide, AI advises and executes**

On this point I disagree with the commissioner. Delegating operational control to a larger AI would separate ownership from control and create a single point of failure: whoever shapes that AI's objectives effectively rules.

Instead, the fund is run by a board directly elected by stakeholders on staggered terms, with four checks on it:
- The board publishes every shareholder vote and its reasons.
- A petition by a set share of stakeholders forces a recall election for any director.
- Stakeholders vote periodically on binding voting guidelines for issues like pay and environmental risk.
- An independent auditor and ombudsman hear challenges.

AI runs analysis, compliance, and routine execution under human sign-off, with open logs.

**5. Transition: build, train, and phase in**

Government builds the foundations markets underprovide: energy, compute, data infrastructure, and training. It takes equity stakes in return for public money that de-risks private automation. Displaced workers get paid retraining and a guaranteed service place.

The phase-in runs over roughly twenty years:
1. Create the fund and stakes, with the levy at its starting rate.
2. Start a small basic income paired with housing reform, with the capital-side backstop in law from the start.
3. Raise the levy and royalties on a published schedule.

That schedule is set by an independent statistics office, insulated like a central bank, using a defined displacement index: the decline in labor's share of national income and in hours worked per adult. Parliament can slow the schedule only by supermajority.

**On capitalism and the alternatives**

Worker ownership leaves out people outside the firm, and automated firms with few workers are exactly where returns will concentrate. Broad public ownership has a poor record at innovation. Tax-funded basic income alone can work, but gives citizens no compounding claim on future output and must be refought every budget.

This model keeps competition, prices, and private enterprise while changing who owns the returns, and it welcomes cooperatives within it. It is capitalism's next form. In this room's judgment it is the arrangement most likely to keep democratic consent through automation, though not the only one that could.
```

## Standings turns

- `sessions/024s1-saint-economics/r2-standings.md` (copy of `records/024s1-saint-economics-r2-standings.md`)
- `sessions/024s1-saint-economics/r3-standings.md` (copy of `records/024s1-saint-economics-r3-standings.md`)

---

A record, not an endorsement. The scribe holds no vote.

SAINT decision record: agreement, not verification.
