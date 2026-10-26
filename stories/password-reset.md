# US-102: Reset a forgotten password

**As a** registered user who forgot my password
**I want** to reset it from the sign-in page
**so that** I can get back into my account without calling support.

## Acceptance criteria

1. The sign-in page has a "Forgot password?" link that opens a form asking for the account email address.
2. For any email address entered, the page shows the same message: "If an account exists for this address, we have sent a reset link."
3. A reset link expires 30 minutes after it is sent and can be used only once.
4. The new password must be at least 12 and at most 64 characters long and contain at least one letter and one digit.
5. No more than 5 reset emails are sent for the same address in any 60-minute window; further requests show the same message but send no email.
6. A successful reset signs the user out of all other sessions.
7. The reset email should arrive promptly.

## Notes

- The message in AC 2 is deliberately identical for known and unknown addresses, so the form cannot be used to find out who has an account.
