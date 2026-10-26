# US-103: Role-based access to finance reports

**As a** finance administrator
**I want** each role to see only the reports it is allowed to see
**so that** salary and transaction data stay with the people who need them.

## Acceptance criteria

1. A Viewer can open the Monthly Summary report only; other reports do not appear in the Viewer's report list.
2. An Analyst can open the Monthly Summary and Transaction Detail reports.
3. A Finance Manager can open every report, including Payroll.
4. Opening a report's URL directly without permission returns HTTP 403 and shows the message "You don't have access to this report".
5. Each denied access attempt is written to the audit log with the user id, report id and timestamp.
6. A role change takes effect at the user's next sign-in; a session that is already open keeps the old permissions until then.
7. The Payroll report shows the viewer's email address as a watermark on every page.

## Notes

- Roles are assigned by an administrator; a user has exactly one role.
