# US-104: Attach supporting documents to an insurance claim

**As a** policyholder filing a claim
**I want** to upload photos and documents to the claim
**so that** the assessor has the evidence without asking me again.

## Acceptance criteria

1. Accepted file types are PDF, JPG and PNG; any other type is rejected with the message "File type not supported".
2. A single file must be at most 10 MB; a larger file is rejected with the message "File is larger than 10 MB".
3. A claim can have at most 5 files attached; the Upload button is disabled while 5 files are attached.
4. The file type is checked from the file's content, not only its extension; an executable renamed to .pdf is rejected as "File type not supported".
5. A file name can be at most 100 characters long, including the extension; a longer name is rejected with the message "File name is too long".
6. Attached files are listed with their name, size and upload date, newest first.

## Notes

- Sizes use binary units: 1 MB = 1,048,576 bytes.
