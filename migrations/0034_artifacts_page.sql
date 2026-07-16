-- 0034_artifacts_page.sql — the "Artifacts" page (?page=artifacts): the wiring that makes ticket
-- #458's <<<ArtifactRegistry>>> invocator reachable. The tag was merged INERT — nothing invoked it,
-- so ?page=artifacts answered "No such page — the DocumentID you asked for isn't in the database".
-- This migration is that invocation.
--
-- Mirrors ?page=forge / ?page=omni / ?page=bugs (0021/0022/0023/0025) exactly, and 0023 states the
-- shape outright: a Document_Templates row holds the page shell (nav via <<<SiteMap>>>) and splices
-- in the invocator; a Documents row binds the slug to that template. WIRING ONLY — no schema change,
-- no new table, no data. The registry table `ticket_artifacts` and its governed `artifact.record`
-- route already exist (0014_ticket_artifacts.sql:7-26) and the rows on it are #455's (20 rows,
-- kind='forge-vm'). Additive: this file creates two rows and touches nothing that exists.
--
-- The tag is checkouts/current/congruency/invocators/tags/dev/ArtifactRegistry.php. Its own header
-- names this file's job and disclaims it: "a Document_Templates row holds the page shell and a
-- Documents row binds the slug to it ... That binding is data, not this tag" (ArtifactRegistry.php:
-- 88-93). It is read-only, so nothing below grants it any write it did not already have.
--
-- ── TemplateID 106: ALLOCATED PAST THE MAX, AND FIXED ON PURPOSE ────────────────────────────────
-- Measured against the live state db this session: Document_Templates holds 27 rows and
-- MAX(TemplateID) is 105. Every id in use, listed rather than summarised as a range because the
-- ranges have holes: 1-5, 10-15 and 100-105 are seeded (17 rows), and 90-99 belong to the page
-- migrations (10 rows) — 0007 -> 90, 0016 -> 91, 0017 -> 92, 0018 -> 93, 0019 -> 94, 0021 -> 95,
-- 0022 -> 96, 0023 -> 97, 0025 -> 98, 0028 -> 99. The migrations' own 90-99 band is FULL, which is
-- why this page does not continue it. 106 is free and collides with nothing.
--
-- It is a FIXED literal rather than a computed MAX(TemplateID)+1 because idempotency needs a stable
-- address: MAX+1 would allocate a SECOND template on a second application, and the Documents row
-- would then point at whichever one ran last. A literal PK is what makes INSERT OR REPLACE land on
-- the same row every time — the same reason 0021/0022/0023/0025 each hardcode theirs.
--
-- ── SELF-CONTAINED ──────────────────────────────────────────────────────────────────────────────
-- CREATE ... IF NOT EXISTS the two base CMS tables so this file applies to a bare db (a fresh seed /
-- the migration-isolation shadow), not only to one that already has them. The column lists are
-- copied from 0025_shadowforge_page.sql:15-22 (identical in 0023_bug_catalog.sql:67-74). On a db
-- that already has the tables both statements are no-ops — CREATE IF NOT EXISTS never alters an
-- existing table, so the live Documents keeps exactly the columns it has today.
--
-- ── IDEMPOTENT ──────────────────────────────────────────────────────────────────────────────────
-- Both inserts are INSERT OR REPLACE keyed on a PRIMARY KEY this file names as a literal
-- (Document_Templates.TemplateID = 106; Documents.DocumentID = 'artifacts'), so a second application
-- rewrites the same two rows with the same bytes: no row is duplicated and no TemplateID is
-- collided with. Measured on a copy of the live db: one application leaves Documents at 27 rows and
-- Document_Templates at 28; a second application leaves both counts unchanged and the whole-db
-- content hash identical to the first result.
--
-- setup.py's do_migrate() is a second, independent guard: it records each applied file in
-- schema_migrations and skips it thereafter (setup.py:413-421), so the MIGRATOR never re-executes
-- this file at all. The OR REPLACE above is what makes a direct re-application safe as well.
--
-- ── THE NAV: WHAT THIS FILE DELIVERS, AND THE ONE HALF IT CANNOT ────────────────────────────────
-- The nav is DERIVED, not stored. <<<SiteMap>>> reads `SELECT DocumentID FROM Documents` and renders
-- one link per page that exists (SiteMap.php:29,40-48), so the Documents row below IS the nav entry:
-- no second nav mechanism is invented here, and none is needed for the link to exist. Measured on a
-- live boot against a copy of the live db with this file applied — every page's nav gains
--     <a href='?page=artifacts'>artifacts</a>
-- and the link resolves to this page.
--
-- WHAT IT DOES NOT REACH, said plainly rather than left to be discovered: the entry's POSITION and
-- its capitalised label. SiteMap renders the ids named in its `$order` literal first, in that
-- literal's sequence, then appends every other page as an "extra" (SiteMap.php:38,41-42); each
-- link's text comes from its `$label` literal, falling back to the raw id (:35-37,:46). Both are PHP
-- source literals and 'artifacts' is in neither, so the entry lands LAST — after Database — reading
-- 'artifacts'. The label is cosmetic (<<<Style>>> sets nav{text-transform:uppercase}, so it renders
-- "ARTIFACTS", exactly as 'forms'/'tickets'/'memories' render through the same fallback). The
-- POSITION is not: the ticket asks for it beside Forge / Omni-git, and it is at the tail.
--
-- No SQL can edit a PHP literal, and this is not a gap a better migration would close. The siblings
-- this file mirrors did that half as a SOURCE CHANGE COMMITTED ALONGSIDE, and each says so in its
-- own header: "SiteMap.php adds 'omni' to the nav order (source change, committed alongside)"
-- (0022_omni_page.sql:8-9), and the same sentence for 'shadowforge' (0025_shadowforge_page.sql:8-9).
-- #459's deliverable is this one .sql file and its mandate is "touch nothing else", so that half is
-- outside this artifact's scope and is NOT delivered here. Reporting it is the point: #458 shipped a
-- component whose caller its own ticket forbade, and the next reader should not have to re-discover
-- this boundary from a rendered page.
--
-- The follow-up is two tokens, both in checkouts/current/congruency/invocators/tags/dev/SiteMap.php:
--     :35-37   add   'artifacts' => 'Artifacts'   to $label   (beside 'omni' => 'Omni-git' on :37)
--     :38      add   'artifacts'                  to $order,  between 'omni' and 'shadowforge'
-- MEASURED, not predicted: with those two tokens applied to a COPY of SiteMap.php (TAGS_DIR pointed
-- at the copy, the repo's file untouched) and THIS db, the nav renders
--     ... Graphs / Source / Forge / Omni-git / Artifacts / Shadow Forge / Memory Graph ...
-- which is where the ticket places it, no other entry moves, and the lowercase tail entry is gone.
-- This migration needed no change for that: SiteMap picks the page up from the Documents row below
-- either way, and $order only decides where it sits.

CREATE TABLE IF NOT EXISTS Document_Templates (TemplateID INTEGER PRIMARY KEY, Content TEXT);
CREATE TABLE IF NOT EXISTS Documents (
  DocumentID  TEXT PRIMARY KEY,
  TemplateID  INTEGER,
  Title       TEXT,
  Description TEXT,
  ContentID   INTEGER
);

-- The page shell: the same skeleton every sibling template uses — <<<TitleTag>>> and <<<Style>>> in
-- <head> (the title comes from the Documents row below), the shared nav, then the body splicing in
-- <<<ArtifactRegistry>>>. The tag renders all three of its views (the kind index, ?kind=<k>, and
-- ?sha=<sha>) into this one slot off $_GET, so one template serves the whole page.
INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (106,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Artifacts</h1>
<p>The ticket-side artifact registry &mdash; congruency holds the metadata and the provenance, the forge holds the blob. Kind is the tag: open a kind to list its artifacts, or an artifact to see every location its content sha is registered at.</p>
<<<ArtifactRegistry>>>
</body>
</html>');

-- The slug: 'artifacts' -> template 106. ContentID mirrors TemplateID exactly as every sibling sets
-- it (measured on the live db: forge -> 95, omni -> 96, bugs -> 97, shadowforge -> 98,
-- memgraph -> 99). The field is inert on the ?page= path and is set only to match the siblings: its
-- one reader is ContentDAO, which selects from a `Content_Blocks` table THIS DB DOES NOT HAVE — the
-- only content table present is `Store_Content_Blocks`, which holds 0 rows and which this migration
-- deliberately does not touch. Nothing below depends on either.
INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'artifacts', 106, 'Artifacts &middot; Congruency', 'The ticket-side artifact registry &mdash; kinds, artifacts, and every location a content sha is registered at', 106
);
