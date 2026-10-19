# English HD IPTV automation

The GitHub Actions workflow runs daily and can be triggered manually.

It retrieves IPTV-org metadata for English channels in New Zealand, the US, the UK and Canada. It checks selected streams with ffprobe, accepting only video at 1280x720 or higher.

## Approval policy

Configure repository variable ENGLISH_HD_APPROVED_HOSTS as a comma-separated list of first-party stream hostnames that you have independently confirmed permit public use. With no approved hosts, no new streams will be added. IPTV-org inclusion alone does not establish authorization.

## Outputs

- english_hd.m3u: validated English HD entries
- live_config.m3u: existing channels plus the separate 英文高清 group
- english_hd_verification.csv: probe results

The script retains existing channels, and preserves previously accepted English HD entries if a run finds no valid replacements. Successful checks from GitHub servers do not guarantee playback from New Zealand.

## Run

Actions > Refresh English HD > Run workflow.
