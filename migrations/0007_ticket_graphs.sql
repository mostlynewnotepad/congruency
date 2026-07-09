-- 0007_ticket_graphs.sql — the "Graphs" page: a top-level header entry that enters the list of
-- ticket-graphs (the provenance explorer). Data-driven like every other page: a Document_Templates
-- row holds the page shell (nav via <<<SiteMap>>>) and splices in the <<<TicketGraphList>>> invocator,
-- and a Documents row 'graphs' binds the slug to that template. SiteMap.php adds 'graphs' to the nav
-- order (source change, committed alongside). High, fixed ids (90) so INSERT OR REPLACE is idempotent
-- and never collides with the seeded templates. Additive.

INSERT OR REPLACE INTO Document_Templates (TemplateID, Content) VALUES (90,
'<!DOCTYPE html>
<html>
<head>
<<<TitleTag>>>
<<<Style>>>
</head>
<body>
<nav><<<SiteMap>>></nav>
<h1>Ticket graphs</h1>
<p>Every ticket as the root of its provenance graph &mdash; goal, patch, approval, runs and (as the ticket-class build lands) mandate, manifestations, guarantees, journey, artifacts and children. Rendered through the &lt;&lt;&lt;TicketGraphList&gt;&gt;&gt; tag.</p>
<<<TicketGraphList>>>
</body>
</html>');

INSERT OR REPLACE INTO Documents (DocumentID, TemplateID, Title, Description, ContentID) VALUES (
  'graphs', 90, 'Graphs &middot; Congruency', 'Provenance explorer — every ticket as a graph', 90
);
