# Prompt Template: Affiliate Linker

Use this with OpenClaw:

openclaw agent --agent researcher --message "Read /Users/ray/Documents/Rayviews/agents/workflows/affiliate_linker_playbook.md and episode files for <slug>. Generate /Users/ray/Documents/Rayviews/content/<slug>/affiliate_links.md with one valid Amazon affiliate link per ranked product. For each product, click yellow SiteStripe 'Get link', capture popup URL with tag=, then close product tab. If any link cannot be generated, mark BLOCKER and stop downstream publish steps."
