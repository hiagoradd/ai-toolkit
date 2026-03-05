Address review comments on the following PR: $ARGUMENTS

## Context

- This skill reads open review comments from a GitHub PR, applies code fixes, and drafts reply messages for each comment
- If `CLAUDE.md` or `.claude/rules/` exist in the repo, read and follow them. If they are absent, skip silently and apply general best practices

## Steps

1. **Resolve the PR.** If `$ARGUMENTS` is provided, use it directly as the PR number or URL. Otherwise, detect the PR from the current branch:
   ```bash
   gh pr view --json number,url,title
   ```
   If no PR is found for the current branch, stop and ask the user to provide a PR number or URL.

2. **Fetch the PR comments** using the GitHub CLI:
   ```bash
   gh pr view <PR> --comments --json reviews,comments,reviewThreads
   ```
   Read the output carefully. Identify every unresolved review comment — inline code comments and top-level review comments.

3. **Enter plan mode. Do NOT make any changes yet.** Categorize every comment into one of:
   - ✅ **Clear fix** — the required change is unambiguous
   - ❓ **Ambiguous** — the intent or correct solution is unclear
   - 💬 **Discussion only** — no code change needed, just a reply (e.g. questions, praise, acknowledgements)

4. **Present the comment triage to the user and stop.** Show the full table, then surface every ambiguous comment with its file location and ask explicitly what change should be made. Do not proceed until the user has answered every ambiguous comment.

   > Here are the review comments I found:
   >
   > | # | Reviewer | File | Comment | Category |
   > |---|----------|------|---------|----------|
   > | 1 | @alice | `src/features/foo/hooks/use-foo.ts:42` | "This should use useCallback" | ✅ Clear fix |
   > | 2 | @bob | `src/features/foo/components/Foo.tsx:18` | "Not sure this pattern is right here" | ❓ Ambiguous |
   > | 3 | @alice | _(top-level)_ | "Overall looks good, just a few nits" | 💬 Discussion only |
   >
   > **Ambiguous comments I need your input on before I can proceed:**
   >
   > **#2 — @bob:** "Not sure this pattern is right here"
   > File: `src/features/foo/components/Foo.tsx:18`
   > What change would you like me to make here?

   **Wait for the user to answer all ambiguous comments. Do not continue to step 5 until they do.**

5. **Present the confirmed plan and stop.** Show what you are about to change for every clear-fix and now-clarified comment. Ask the user to confirm before touching any file.

   > Here is my plan:
   >
   > | # | File | Change |
   > |---|------|--------|
   > | 1 | `use-foo.ts:42` | Wrap handler in `useCallback` with correct dependency array |
   > | 2 | `Foo.tsx:18` | [change as clarified by user] |
   >
   > Shall I proceed?

   **Wait for explicit user confirmation. Do not apply any changes until the user says yes.**

6. **Apply code fixes** for all clear-fix and clarified comments.
   - Read the full file before editing — never patch blindly from the comment alone
   - Make the minimal change that addresses the comment
   - Do not refactor, reformat, or improve code outside the scope of the comment
   - Do not fix multiple comments in a single edit if they touch the same file — apply them one at a time to avoid conflicts

7. **Draft a reply for every comment** (clear fix, ambiguous, and discussion-only):
   - For fixed comments: confirm what was changed, briefly
   - For discussion-only comments: write a natural, concise acknowledgement or answer
   - Keep replies short and professional — no filler phrases like "Great point!" or "Thanks for the feedback!"
   - Write in first person as the PR author

8. **Present the reply drafts to the user for review:**

   > Here are the draft replies:
   >
   > ---
   > **#1 — @alice** · `use-foo.ts:42`
   > > "This should use useCallback"
   >
   > ✅ Fixed. Wrapped the handler in `useCallback` with the correct dependency array.
   >
   > **Reply draft:**
   > "Done — wrapped in `useCallback`."
   >
   > ---
   > **#3 — @alice** · _(top-level)_
   > > "Overall looks good, just a few nits"
   >
   > 💬 No code change needed.
   >
   > **Reply draft:**
   > "Thanks for the review — addressed all the nits above."
   >
   > ---
   >
   > Would you like to adjust any replies before I post them?

   **Wait for confirmation or edits from the user before posting anything.**

9. **Post the replies** using the GitHub CLI once the user approves:
   ```bash
   gh api repos/{owner}/{repo}/pulls/comments/{comment_id}/replies \
     -f body="<reply text>"
   ```
   Post each reply to its corresponding comment thread.

## Ambiguous Comment Handling

Never guess at the intent of an unclear comment. Always surface it in step 4 with the full comment text and file location, and ask explicitly what change (if any) should be made. Only proceed with the fix after receiving a clear answer.

## Reply Tone Guidelines

- Confirm changes factually: "Done — extracted into a separate hook."
- Answer questions directly without over-explaining
- For subjective comments where you disagree or want to discuss: draft a reply that opens a dialogue rather than blindly accepting
- Never use: "Great catch!", "Thanks for the feedback!", "Absolutely!", or similar filler

## What NOT to Do

- Do not resolve comment threads — let the reviewer do that
- Do not push commits or open new PRs
- Do not change files unrelated to a review comment
