package tags

// titletag.go — ticket #343, unit go-port:tags:tag:TitleTag.
//
// The Go port of ONE tag: invocators/tags/document/TitleTag.php. Per #281 a tag port is
// ADD-A-FILE-ONLY: this file holds the tag's type, its constructor, its GetDocument, its helpers and
// its self-registration (the init() below), and it changes NOTHING in engine.go — the registry picks
// the tag up because Go runs every init() in a package before any other code in it
// (engine.go:1355 Register, engine.go:1393 newTag). Every identifier it defines is titleTag*-
// prefixed or TitleTag*-named, so it cannot collide with the sibling tag ports.
//
// THE CONTRACT: byte-identical HTML. The PHP is the SPEC. Where the two disagree THIS file is wrong.
//
// ── THE WHOLE TAG (TitleTag.php:7-22) ───────────────────────────────────────────────────────────
//
//	class TitleTag implements Tag_Interface{
//	    private $arguments; private $title;
//	    public function __construct($arguments){
//	        $this->arguments = $arguments;                                   // :13 (stored, never read)
//	        $document = PersistentObjectManager::getData('WORKING_PAGE');    // :14
//	        $this->title = $document->getTitle();                            // :15
//	    }
//	    public function get_document(){
//	        return "<title>" . $this->title . "</title>";                    // :19
//	    }
//	}
//
// Three facts decide this port, and each was MEASURED against the live PHP this session rather than
// reasoned about:
//
//  1. It takes NO arguments. $arguments is assigned at :13 and never read again — not by
//     get_document(), not by a helper. There is no ->top(), no ->pop(). So the argument-less gallery
//     render and every <<<TitleTag>>> template render run the IDENTICAL code path, and this tag has
//     no argument forms to port. (Contrast ContentTag, whose :15 `$arguments->top()` is what makes
//     its standalone render an error path — see contenttag.go's header.)
//
//  2. It does NO escaping. :19 concatenates $this->title RAW into the markup — no htmlspecialchars,
//     no esc(). This is not an inference: the live 'tags' document's Title is the literal db text
//     "Tags &middot; Congruency" (read straight out of the state db this session), and the live page
//     emits it byte-for-byte unchanged. Had :19 escaped, the page would carry "Tags &amp;middot;
//     Congruency". It does not. So esc() here would be a divergence, and it is deliberately absent.
//
//  3. It touches NO database of its own and emits no wrapper, no header and no empty-state text. Its
//     whole output is one <title> element around one string.
//
// ── THE GALLERY RENDER IS THE HAPPY PATH, NOT AN ERROR PATH ─────────────────────────────────────
//
// The gate URL is ?page=tags&tag=TitleTag, and TagList constructs the selected tag with NULL —
// `$obj = new $sel(null);` (TagList.php:67). For ContentTag that NULL is fatal. For TitleTag it is
// HARMLESS, because :13 only STORES $arguments and nothing ever reads it back. Nothing in this tag
// dereferences the NULL, so no Error is thrown and TagList's catch (TagList.php:69-72) never fires.
//
// What the tag needs instead is WORKING_PAGE, and on this path it IS set. Controller::display sets
// it BEFORE it renders anything (Controller.php:30-39):
//
//	$document = DocumentManager::get_document( $document_id );   // :31
//	PersistentObjectManager::setData('WORKING_PAGE',$document);  // :37  <- set here
//	self::set_display_string($document->__toString());            // :38  <- tags render here
//
// :38 is what runs the tag engine, so by the time TagList reaches :67 and builds TitleTag, the POM
// already holds the 'tags' Document. TitleTag therefore renders the TAGS PAGE'S OWN TITLE.
//
// MEASURED off the live PHP server this session — the ?page=tags&tag=TitleTag page cut between
// TagList.php:62's heading anchor and its :76 close (the same slice equivalence_test.go cuts) is
// EXACTLY these 39 bytes:
//
//	<title>Tags &middot; Congruency</title>
//
// A cross-check that the working page really is the REQUESTED page and not a constant: that same
// page carries this element TWICE — once from the 'tags' template's own <<<TitleTag>>> and once from
// the gallery slice — and the two are identical. The gallery render and the in-page substitution are
// the same render.
//
// ── RESOLVING WORKING_PAGE WITHOUT A POM ────────────────────────────────────────────────────────
//
// This package has no PersistentObjectManager — engine.go's divergence 3, and Render() says so
// outright: "PHP's PersistentObjectManager::setData('WORKING_PAGE', $document) and
// ::executeCommands() have no counterpart here" (engine.go:4124-4125). So the value :14 reads out of
// the POM has to be RE-DERIVED here. It can be, exactly, because the POM is not a cache of something
// unknowable: WORKING_PAGE is a pure function of $_GET['page'], written once per request by the only
// line that writes it (Controller.php:37 is the ONLY setData('WORKING_PAGE') in the checkout).
//
// titleTagWorkingPage replays that function — Controller::control's key choice (Controller.php:15-19)
// then DocumentManager::produceDocument's lookup-with-fallback (DocumentManager.php:42-53):
//
//	if(isset($_GET['page'])){ $post_validated = ValidateFields::validatePageKey($_GET['page']); }
//	else                    { $post_validated = "catalog"; }                    // Controller.php:15-19
//
//	$documentData = $this->documentDAO->getDocumentData($key);                  // DocumentManager.php:44
//	if(isset($documentData)){ $document = Document::sql_assoc_array($documentData); }
//	else{
//	    $documentData = $this->documentDAO->getDocumentData("invalid");         // :48  <- the fallback
//	    if($documentData){ $document = Document::sql_assoc_array($documentData); }
//	}
//
// The fallback at :48 is the part that is easy to miss and is REAL, not defensive padding. Every
// branch below was measured against the live PHP this session by reading the page's own <title>:
//
//	?page=tags           -> <title>Tags &middot; Congruency</title>     the requested document
//	?page=about          -> <title>About &middot; Congruency</title>    tracks the request
//	?page=catalog        -> <title>Congruency Lives</title>             tracks the request
//	?page=zzznosuchpage  -> <title>Page not found</title>               valid key, no row  -> 'invalid'
//	?page=tags2          -> <title>Page not found</title>               validatePageKey NULL -> 'invalid'
//	?page=a              -> <title>Page not found</title>               1 letter, invalid  -> 'invalid'
//	?page=               -> <title>Page not found</title>               isset() TRUE, validate NULL
//
// The last two rows are why the key is passed to GetDocumentByKey RAW rather than pre-validated
// here. PHP validates TWICE — once at Controller.php:16 and again inside the DAO
// (DocumentDAO.php:39, `$key = ValidateFields::validatePageKey($key); if(isset($key)){...}`) — and
// GetDocumentByKey already performs that same validation (engine.go:1103). Collapsing the two into
// one is safe because validatePageKey is idempotent: a valid key validates to itself, and an invalid
// one yields NULL on the first pass and no row on the second, which lands on the SAME 'invalid'
// fallback either way. Both sides agree on all seven rows above.
//
// `?page=` deserves one note: PHP's isset($_GET['page']) is TRUE for an empty value, so
// Controller.php:16 (not :18) runs and validatePageKey("") returns NULL. getIsset models exactly
// that isset-vs-value distinction (engine.go:923-935), and validatePageKey("") returns ok=false
// (engine.go:1074-1086), so "" takes the fallback here just as it does on the live server. Reading
// $_GET['page'] with getStr would have collapsed absent and empty together and mapped "" onto
// "catalog" — the wrong title, and a real divergence.
//
// ── WHY THE WORK IS IN GetDocument RATHER THAN THE CONSTRUCTOR ──────────────────────────────────
//
// PHP does the lookup in the CONSTRUCTOR (:14-15); this file does it in GetDocument. That moves no
// observable byte, and it is the same choice — for the same documented reason — that contenttag.go
// makes (see its header): a Go factory (`func(e *Engine, args *TagArguments) Tag`, engine.go:1355)
// cannot fail, and TagList wraps the `new` AND the get_document() call in ONE try (TagList.php:66-72)
// so both statements land in the same catch. Deferring also keeps construction free of I/O, which is
// what lets SelfCheck build every registered tag with an empty Config (engine.go:4377) without
// touching a database.
//
// ── THE ONE BRANCH THAT IS NOT MEASURED, AND IS NOT REACHABLE ───────────────────────────────────
//
// If WORKING_PAGE were NULL, :15's `$document->getTitle()` would be a fatal Error. On the PHP side
// that state cannot arise: Controller.php:38 calls `$document->__toString()` on the very same value
// one line after storing it, so a NULL there fatals the whole page BEFORE any tag runs — the tag
// would never be constructed, and there would be no bytes to reproduce. Confirmed against the live
// server: this tag renders its 39 bytes and appears in NO error notice; the only standalone notices
// the whole gallery emits today are five `top() on null` ones (CategoryView, Config_Form_Invocator,
// ContentTag, ProductView, TestTagA), and TitleTag is not among them.
//
// The Go counterpart — titleTagWorkingPage returning nil — needs BOTH the requested key AND
// 'invalid' to fail to resolve, i.e. an unreadable db or a db with no 'invalid' row. The live state
// db has one ('invalid' -> Title "Page not found", read this session). So the branch below is dead
// on every surface either engine has.
//
// It is ported anyway, as what TitleTag.php's OWN code does when handed a NULL $document: :15 throws
// and TagList's catch renders the notice. titleTagNullPageError's wording is DERIVED, not measured —
// PHP 8's message template is "Call to a member function <method>() on null", confirmed on this
// exact server by all five notices above (each with method `top`); only the method name differs.
// Since no reachable input produces it, the derivation cannot affect the gate.

// init self-registers the tag; this is the whole wiring step (#281; engine.go:1355, 1393-1401).
// PortedTags() is registry-derived (engine.go:1406-1415), so it picks this up with no edit there.
// Register is the registry's only writer and PANICS on a duplicate name, so this is the ONE place
// "TitleTag" is registered.
func init() {
	Register("TitleTag", func(e *Engine, a *TagArguments) Tag { return newTitleTagTag(e, a) })
}

// TitleTagTag is TitleTag (TitleTag.php:8-21). The doubled "Tag" is the package convention
// (<TagName>Tag) applied to a tag whose own name already ends in "Tag" — the same shape
// ContentTagTag has.
//
// The PHP's two properties are $arguments and $title. NEITHER is carried:
//
//   - $arguments (:13) is assigned and never read, so porting it would be a field no code touches.
//   - $title (:15) is the constructor's computed result; because that computation is deferred to
//     GetDocument (see the file header), there is nothing to hold between the two calls.
//
// So the engine is the whole state: it carries $_GET (which selects the working page) and the
// Config (which names the db that resolves it).
type TitleTagTag struct {
	e *Engine
}

// newTitleTagTag is TitleTag::__construct (TitleTag.php:12-16), minus the WORKING_PAGE lookup that
// GetDocument now does.
//
// args is accepted and DISCARDED, which is faithful rather than lazy: :13 stores $arguments into a
// property that nothing ever reads. That is also why nil args — the gallery's `new $sel(null)`
// (TagList.php:67) — is harmless here and needs no ctorThrew flag: this tag never dereferences it.
//
// It must never panic: SelfCheck constructs registered tags with nil args and an empty Config
// (engine.go:4377-4378).
func newTitleTagTag(e *Engine, args *TagArguments) *TitleTagTag {
	return &TitleTagTag{e: e}
}

// titleTagNullPageError is get_class($e).': '.$e->getMessage() for the Error TitleTag.php:15 would
// throw if PersistentObjectManager::getData('WORKING_PAGE') returned NULL.
//
// DERIVED, NOT MEASURED — and unreachable. See the file header's last section: no input to either
// engine produces it, so nothing on the gate depends on this string being right. The template is
// PHP 8's "Call to a member function <method>() on null", which this same live server demonstrates
// five times over with method `top` (contenttag.go:199 carries one such MEASURED instance).
const titleTagNullPageError = "Error: Call to a member function getTitle() on null"

// titleTagStandaloneHTML is TagList.php:70-71's catch body, verbatim:
//
//	"<p style='color:#b00020'>This tag needs context to render standalone: "
//	  . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</p>"
//
// The message is run through esc() — this package's htmlspecialchars($s, ENT_QUOTES) port
// (engine.go:599) — rather than hand-escaped, because that is the IDENTICAL call TagList::esc
// (TagList.php:20) makes on the IDENTICAL value, so the two cannot drift apart.
//
// Note this is the ONLY place this file escapes anything, and it is escaping TagList's bytes, not
// TitleTag's: the tag's own :19 concatenates its title raw (file header, fact 2).
//
// There is NO trailing newline: TagList.php:71 ends at "</p>".
func titleTagStandaloneHTML() string {
	return "<p style='color:#b00020'>This tag needs context to render standalone: " +
		esc(titleTagNullPageError) + "</p>"
}

// titleTagWorkingPage is PersistentObjectManager::getData('WORKING_PAGE') (TitleTag.php:14)
// re-derived from $_GET, since this package has no POM (engine.go:4124-4125, divergence 3).
//
// It replays the two PHP steps that jointly produce that value — Controller::control's key choice
// (Controller.php:15-19) and DocumentManager::produceDocument's lookup-with-'invalid'-fallback
// (DocumentManager.php:42-53). Both are spelled out, with the measured evidence for every branch, in
// the file header. nil is PHP's NULL $document.
func (t *TitleTagTag) titleTagWorkingPage() *Document {
	// Controller.php:15-19 — isset($_GET['page']) picks the key; its ABSENCE (not its emptiness)
	// is what defaults to "catalog", which is why this reads getIsset and not getStr.
	pageKey := "catalog"
	if v, ok := t.e.getIsset("page"); ok {
		pageKey = v
	}

	// DocumentManager.php:44-46 — the requested document. GetDocumentByKey folds in the DAO's own
	// validatePageKey (DocumentDAO.php:39) and its `$rows == 1` test (DocumentDAO.php:47), so its
	// error is exactly the PHP's `!isset($documentData)`.
	if doc, err := t.e.GetDocumentByKey(pageKey); err == nil {
		return doc
	}

	// DocumentManager.php:48-50 — the fallback. An unresolvable key does NOT mean "no working page";
	// it means the 'invalid' document, whose Title is "Page not found" on the live db.
	if doc, err := t.e.GetDocumentByKey("invalid"); err == nil {
		return doc
	}

	// Both lookups failed — an unreadable db or one with no 'invalid' row. PHP reaches this only in
	// a state where Controller.php:38 has already fatalled the page. See the file header.
	return nil
}

// GetDocument is TitleTag::get_document() (TitleTag.php:18-20) PLUS the constructor work (:14-15)
// that a Go factory cannot perform:
//
//	return "<title>" . $this->title . "</title>";
//
// The title is concatenated RAW — no esc(), by measurement, not by omission (file header, fact 2).
//
// It deliberately has NO `defer catchThrowable(...)`: TitleTag.php has no try and no catch, so
// adding one would invent a cy-form-error branch the PHP can never emit. Same call this file's
// sibling ports make, and the same reason contenttag.go gives.
func (t *TitleTagTag) GetDocument() string {
	doc := t.titleTagWorkingPage()
	if doc == nil {
		// TitleTag.php:15 on a NULL $document — the constructor throws and TagList's catch
		// (TagList.php:69-72) supplies the bytes. Unreachable; see the file header.
		return titleTagStandaloneHTML()
	}

	// Document::getTitle() (Document.php:43-45) — $this->documentTitle, mapped from the row's Title
	// column by sql_assoc_array (Document.php:26) and already phpString'd by GetDocumentByKey
	// (engine.go:1163), so a NULL Title arrives as "" exactly as PHP's `"<title>" . NULL` does.
	return "<title>" + doc.Title + "</title>"
}
