# Job Alert Dashboard PRD

## Business Goal

Help job seekers track AI automation and QA job opportunities from multiple sources in one dashboard so they can apply faster and avoid missing important roles.

## Personas

- Job Seeker: Wants to track relevant roles, save interesting jobs, and monitor application status.
- Career Coach: Wants to review saved jobs and suggest next actions.

## Features

- Add, edit, and delete job source URLs.
- Scan saved job sources every morning and collect new job posts.
- Prevent duplicate job posts from being saved.
- Mark jobs as Interested, Applied, Rejected, or Saved.
- Show dashboard counts by status.
- Send a daily email summary with new jobs and pending actions.

## Dependencies

- Email notification service.
- Background scheduler.
- Job source pages must be reachable.
- User account and authentication service.

## Risks

- Some job sites may change page structure.
- Duplicate detection may miss similar job titles.
- Email delivery may fail.

## Assumptions

- User is already logged in.
- A job source URL is valid if it starts with http or https.
- Daily scan runs once every morning.

## Acceptance Criteria

- User can add a valid job source URL.
- User sees a validation error for invalid URLs.
- System stores new job posts without duplicates.
- Dashboard status counts update when a job status changes.
- Daily email summary is sent once per day.

## Demo

- Add a new job source.
- Run the job scan.
- Save an interesting job.
- Mark a job as Applied.
- Show dashboard counts updating.
- Show the daily email summary preview.
