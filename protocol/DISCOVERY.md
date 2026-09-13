# Candidate Discovery Protocol

Candidate Discovery is the continuous process of understanding the person being coached. It is not a one-time questionnaire.

The process maintains three deliberately separate layers:

- `CandidateProfile`: facts, goals, preferences, and materials confirmed by the user.
- `CoachObservation`: an immutable, evidence-backed coaching inference.
- `CoachModel`: a rebuildable projection of current strengths, gaps, risks, and mixed signals.

## Starting a discovery conversation

Before asking questions:

1. Confirm the user's privacy choice during onboarding.
2. Run `python scripts/discover.py status`.
3. Read `workspace/profile/candidate.json` and `workspace/state/coach-model.json` when they exist.
4. Offer the user a choice: talk now, provide a resume, provide other files, or combine these methods.

Prefer materials first. When the user provides a resume or another information file, inspect it, summarize what appears to be true, and ask only about ambiguities or important gaps. Never make the user repeat information already present in their materials.

When discovery happens through conversation, ask one useful question at a time. Cover only what is relevant:

- current background, responsibilities, and experience;
- target role, level, companies, timing, and motivation;
- self-perceived strengths and uncertainties;
- recurring feedback from interviews or work;
- available resumes, notes, question banks, job descriptions, or interview records;
- language, session length, and coaching-style preferences.

## Recording information

Write a fact to `CandidateProfile` only after the user confirms it. Information inferred from a resume or file must first be summarized for confirmation. Record the material itself immediately when the user explicitly provides it.

Write a `CoachObservation` only when an inference is useful beyond the current turn. Every observation must state the signal, confidence, claim, and at least one concrete evidence reference. Do not disguise an inference as a candidate fact.

Rebuild `CoachModel` from observations. Do not edit it as a second source of truth.

Evidence support is conservative:

- one distinct evidence reference: `emerging`;
- two distinct evidence references: `supported`;
- three or more distinct evidence references: `well_supported`.

Only supported or well-supported, non-conflicting signals appear in the model's top-level strengths, gaps, or risks. Conflicting signals remain `mixed` until more evidence resolves them.

## Completion and continued discovery

Initial discovery is complete when all of the following are true:

- at least one discovery method was used;
- the profile contains a background summary or a registered material;
- the user has a current goal, motivation, or explicit open question;
- the user confirms the profile summary.

Discovery continues after onboarding. Revisit the profile and model when the user adds materials, repeatedly succeeds or struggles, completes a baseline or preparation cycle, records a real interview, or changes target roles.

Useful commands:

```text
python scripts/discover.py status
python scripts/discover.py start
python scripts/discover.py update --method conversation --target-role "Senior Data Engineer" --background-summary "..." --confirmed-by-user
python scripts/discover.py add-material --kind resume --path workspace/resume/resume.md
python scripts/discover.py complete --confirmed-by-user
python scripts/coach_model.py observe --dimension technical --subject spark --signal gap --claim "Needs a clearer explanation of shuffle boundaries" --evidence attempt_event=workspace/events/attempt.example.json
python scripts/coach_model.py rebuild
```
