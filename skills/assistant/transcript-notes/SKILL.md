---
name: transcript-notes
description: 'Process meeting transcripts into structured notes with metadata, TL;DR,
  key topics, action items, and quotes. Use when converting raw transcript .txt files
  into formatted .md notes. Triggers on: "process transcript", "generate notes from
  transcript", "transcript to notes", "/transcript-notes".'
metadata:
  category: assistant
  tags:
  - transcript
  - notes
  - meeting
  - documentation
  status: ready
  version: 1
---

# Transcript Notes

Convert a raw meeting transcript `.txt` file into a structured `.md` notes file.

## Prerequisites

- Raw transcript `.txt` file with speaker-turn format (speaker name on its own line, dialogue as paragraph)
- Target notes directory exists or will be created

## Workflow

### 1. Read & Analyze Transcript

- Read the transcript file
- Identify: participants, series name, episode number, date, duration (estimate from content length if not stated)
- Map the conversation flow: what topics were discussed, in what order, by whom

### 2. Extract & Structure

- **Meeting Metadata:** Series, Episode, Date (if inferable), Duration (if inferable), Participants
- **TL;DR:** Single paragraph, 2-4 sentences, captures the meeting's purpose and key outcomes
- **Key Topics:** Each topic gets a `**bold title** -- one-line summary` bullet, then a `###` subsection with 2-5 sentences or bullets expanding it
- **Action Items:** `**Person/Group:** action description` format
- **Quotes:** 3-5 notable quotes using `> "quote" -- Speaker Name (context)` format

### 3. Write & Verify

- Create the notes directory if it doesn't exist: `notes/{series-slug}/`
- Write the `.md` file mirroring the transcript number (e.g., `001.txt` → `001.md`)
- Verify structure matches the output template

## Output Template

```markdown
# {Series Name} - Episode {NNN}

## Meeting Metadata
- **Series:** {series name}
- **Episode:** {NNN}
- **Date:** {date}
- **Duration:** {duration}
- **Participants:** {comma-separated full names}

## TL;DR
{Single paragraph, 2-4 sentences}

## Key Topics
- **{Topic}** -- {One-line summary}
- **{Topic}** -- {One-line summary}
...

### {Topic Heading}
{2-5 sentences or bullet points}

### {Topic Heading}
...

## Action Items
- **{Person/Group}:** {Action description}
...

## Quotes
> "{Quote}" -- {Speaker Name} ({optional context})
...
```

## Quality Rules

- TL;DR must be a single paragraph — no bullets, no multiple paragraphs
- Key Topics bullet list and `###` subsections must correspond 1:1 and appear in the same order
- Action items must name a specific person or group
- Quotes must be actual words from the transcript, not paraphrased
- Use `--` (double dash) not `—` (em dash) for separators in topic summaries and quotes
- Series slug for directory: kebab-case version of series name
- Optional metadata fields (Date, Duration) — include only when inferable from transcript content

## Examples

### Positive Trigger

User: "Process the transcript at transcripts/ai-platform-sync/003.txt into structured notes with metadata and action items"

Expected behavior: Reads the transcript file, extracts participants, topics, action items, and quotes, then writes a structured `.md` notes file.

### Non-Trigger

User: "Summarize this PDF document into bullet points"

Expected behavior: This is a general summarization request, not transcript processing. Use a general-purpose summarization approach instead.

## Troubleshooting

- Error: Cannot determine series name
  - Cause: Transcript has no meeting context or header identifying the series.
  - Solution: Ask user for the series name before proceeding.

- Error: No clear action items found
  - Cause: Meeting was informational only with no commitments or next steps.
  - Solution: Write "No action items identified" in the Action Items section, or extract implicit next steps.

- Error: Cannot estimate duration
  - Cause: No timing cues, timestamps, or length indicators in transcript.
  - Solution: Omit Duration from the Meeting Metadata section.
