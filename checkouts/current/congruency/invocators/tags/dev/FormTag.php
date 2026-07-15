<?php
/*
Copyright (C) 2006 Steven Peterson
Congruency is free software, licensed under the GNU GPLv2 or later.
See the LICENSE file in the project root for full license terms.
*/
/*
 * FormTag — render a stored form by id through the real form pipeline.
 *
 * Usage in document content:  <<<FormTag(OrderForm)>>>
 *
 * The id is a `formName` in the `forms` table. FormTag looks up FORM_MANAGER in the
 * POM and calls runForm() (FormManager.php:28), which builds a StandardForm out of
 * that table (FormElementDAO -> FormElementBean -> produceElement) and renders it.
 * With no id, FormTag renders its own usage instead — see WHY THE ID IS CHECKED HERE.
 *
 * WHY THE ID IS CHECKED HERE FIRST (ticket #160).
 * The pipeline's own validator, ValidateFields::validateFormKey (ValidateFields.php:40-48),
 * runs preg_match("/[a-zA-Z0-9\-\_]+/", $formKey, $result) and then reads $result[0] at line 43
 * without ever checking that the match succeeded. An id holding no [a-zA-Z0-9_-] character
 * anywhere matches nothing, so $result stays an empty array and that read raises
 * "Warning: Undefined array key 0", which PHP prints straight into the page. Measured, on this
 * checkout:
 *
 *     validateFormKey('')            -> NULL, 2 warnings (lines 43 and 44)
 *     validateFormKey('!!!')         -> NULL, 1 warning  (line 43)
 *     validateFormKey('bad id')      -> NULL, no warning  (it matches 'bad', just not the whole id)
 *     validateFormKey('OrderForm')   -> 'OrderForm', no warning
 *
 * The EMPTY id warns twice because $result[0] reads as NULL and '' == NULL is true in PHP, so the
 * guard falls into its own then-branch and reads $result[0] a second time at line 44 to return it.
 * That doubled warning is exactly what #160 quotes.
 *
 * The empty id is not hypothetical. The tag gallery renders every tag standalone with
 * `new $sel(null)` (TagList.php:67), and `<<<FormTag()>>>` in document content parses to an
 * empty argument — both land here with no id. That is the FormTag/render failure
 * tag_selfcheck.py filed as #160.
 *
 * So FormTag hands runForm() ONLY an id that validateFormKey will accept whole, and answers
 * every other id itself, below. The fix is confined to this file: ValidateFields is shared by
 * validatePageKey/validateNumericKey/validateFormKey and their callers, and is not #160's to
 * touch.
 *
 * ID SHAPES.
 * validateFormKey accepts an id made entirely of [A-Za-z0-9_-]. Document content is narrower
 * still: the tag parser's FUNCTION_ARGUMENT is /\([A-Za-z0-9]*\)/, so an id written as
 * <<<FormTag(...)>>> can only be letters and digits. A hyphenated formName such as
 * ConfigForm-6 is a perfectly good form key (FormTag renders it when constructed directly)
 * but cannot be invoked from document content — the tag engine does not recognise the
 * invocation and leaves it as literal text. The usage panel says so rather than offering an
 * id that would not work.
 *
 * Wrapped in try/catch: the tag engine has no error boundary of its own —
 * Tag_Wrapper::execute_all_tags (Tag_Wrapper.php:63-74) calls get_document() uncaught — so a
 * form problem would otherwise take the whole page down.
 */
if (!class_exists("FormTag")) {
    class FormTag implements Tag_Interface {

        /* An id validateFormKey() accepts whole: one or more [A-Za-z0-9_-] and nothing else.
           \z, not $, so a trailing newline cannot slip past — validateFormKey would reject it. */
        const FORM_KEY_RE = '/^[A-Za-z0-9_-]+\z/';

        /* The tag parser's FUNCTION_ARGUMENT charset, used only to label the stored-form list. */
        const TAG_ARG_RE = '/^[A-Za-z0-9]+\z/';

        private $formId;

        public function __construct($arguments) {
            $id = '';
            if (is_object($arguments) && method_exists($arguments, 'pop')) {
                $id = $arguments->pop();      // TagArguments::pop(); NULL once the list is empty
            } elseif (is_string($arguments)) {
                $id = $arguments;
            }
            $this->formId = is_string($id) ? trim($id) : '';
        }

        private static function esc($s) { return htmlspecialchars((string)$s, ENT_QUOTES); }

        private static function note($html) {
            return "<div class='cy-form-note' style='border:1px solid #d8d2c4;border-left:5px solid #8a5a1a;"
                 . "border-radius:6px;padding:.7rem .9rem;background:#fffdf8'>" . $html . "</div>";
        }

        /* The distinct formName values in the `forms` table. Read-only, and the same database the
           form pipeline itself reads: DataConnection::open() uses CONGRUENCY_SQLITE when it is
           defined (DataConnection.php:32), so this list is exactly what runForm() can build. */
        private static function knownForms() {
            $names = array();
            if (!defined('CONGRUENCY_SQLITE') || !is_file(CONGRUENCY_SQLITE)) { return $names; }
            $db = new PDO('sqlite:' . CONGRUENCY_SQLITE);
            $db->setAttribute(PDO::ATTR_ERRMODE, PDO::ERRMODE_EXCEPTION);
            $st = $db->query("SELECT DISTINCT formName FROM forms ORDER BY formName");
            foreach ($st->fetchAll(PDO::FETCH_COLUMN, 0) as $n) {
                $n = trim((string)$n);
                if ($n !== '') { $names[] = $n; }
            }
            return $names;
        }

        /* "Stored forms: a, b, c" — plus, when some id cannot be written as a document tag, a
           plain sentence naming it. Returns '' if the list cannot be read: the caller is already
           explaining something, and a database problem must not replace that explanation. */
        private static function formsLine() {
            try {
                $names = self::knownForms();
            } catch (\Throwable $e) {
                return "";
            }
            if (empty($names)) { return ""; }
            $shown = array();
            $literal = array();
            foreach ($names as $n) {
                $shown[] = "<code>" . self::esc($n) . "</code>";
                if (!preg_match(self::TAG_ARG_RE, $n)) { $literal[] = "<code>" . self::esc($n) . "</code>"; }
            }
            $out = "<p style='margin:.5rem 0 0'>Stored forms: " . implode(", ", $shown) . "</p>";
            if (!empty($literal)) {
                $out .= "<p style='margin:.35rem 0 0;font-size:.85rem;color:#555'>"
                      . implode(", ", $literal) . " cannot be written as a document tag: the tag parser accepts"
                      . " only letters and digits between the parentheses, so such an invocation stays literal text.</p>";
            }
            return $out;
        }

        public function get_document() {
            try {
                if ($this->formId === "") {
                    return self::note("<strong>FormTag</strong> renders a stored form by id. Give it one, e.g."
                                    . " <code>&lt;&lt;&lt;FormTag(OrderForm)&gt;&gt;&gt;</code>." . self::formsLine());
                }
                if (!preg_match(self::FORM_KEY_RE, $this->formId)) {
                    return self::note("<strong>FormTag:</strong> <code>" . self::esc($this->formId) . "</code> is not a usable"
                                    . " form id — an id is one or more letters, digits, <code>-</code> or <code>_</code>,"
                                    . " and nothing else." . self::formsLine());
                }
                $formManager = PersistentObjectManager::getData("FORM_MANAGER");
                if (!isset($formManager)) {
                    return self::note("<strong>FormTag:</strong> no FORM_MANAGER in the POM — the form system is not"
                                    . " initialized, so no form can be built.");
                }
                $html = (string)$formManager->runForm($this->formId);
                /* runForm() reports an unbuildable form by returning FORM_LOAD_FAILURE, an HTML comment
                   (FormManager.php:21,34) — invisible on the page. Say it out loud instead. */
                if (defined("FORM_LOAD_FAILURE") && $html === FORM_LOAD_FAILURE) {
                    return self::note("<strong>FormTag:</strong> no form named <code>" . self::esc($this->formId)
                                    . "</code> is stored." . self::formsLine());
                }
                return "<div class='cy-form'>" . $html . "</div>";
            } catch (\Throwable $e) {
                return "<div class='cy-form-error'>FormTag error: "
                     . self::esc(get_class($e) . ': ' . $e->getMessage()) . "</div>";
            }
        }
    }
}
?>
