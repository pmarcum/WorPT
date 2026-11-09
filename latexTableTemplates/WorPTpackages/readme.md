<b>NOTE:<i> You only need to do this ONCE in your LaTeX document!</i></b>
<p>The WorPT tables need one small package file, <b>worpt.sty</b>, loaded in your document's preamble. It comes with the tables, and it is also here: https://github.com/pmarcum/WorPT/blob/main/latexTableTemplates/worpt.sty</p>
<hr>

<mark><b>How To Load worpt.sty In Your Document</b></mark>
<ol>
<li>Put <code>worpt.sty</code> in the same folder as your document (gooTeX does this for you).</li>
<li>Add this line to your preamble, <b>as the last package loaded</b> (after aastex, xcolor, hyperref and the rest):
<pre><code>
\usepackage{worpt}
</code></pre></li>
</ol>
<p>After that, you can put in as many of the WorPT tables as you want.</p>

<details>
<summary><b>What worpt.sty does</b></summary>
<ul>
<li>It loads only the packages the tables need: array, multirow, xcolor, colortbl, rotating (for tables in landscape mode), and tikz with fontawesome (for the schedule table's icons). A package your document has already loaded is not loaded again.</li>
<li>It defines the named colors the tables use (Blue, NavyBlue, Red, Black, White and mediumelectricblue), with the values xcolor's <code>[dvipsnames]</code> option gives them. A color your document already defines keeps its own value. To use other dvipsnames colors in your table settings, load xcolor with <code>[dvipsnames]</code> before worpt.</li>
<li>It works with AASTeX 7 (aastex702) and aastex631, revtex, article and report, in one or two columns.</li>
<li>It changes nothing else about how your document looks.</li>
</ul>
</details>

<details>
<summary><b>Documents set up before worpt.sty</b></summary>
Documents that load the FUpackages, FUformatting and FUnewCommands files from https://github.com/pmarcum/LaTex-Formatting can keep them: add <code>\usepackage{worpt}</code> after them. The tables no longer need those files, so a document that loaded them only for WorPT can drop them. Older paste-in blocks that use <code>\expinput{...}</code> keep working; <code>\expinput</code> now works the same as <code>\input</code>. A line such as <code>\def\TaskAddCounter{-1}</code> is no longer needed, and does nothing.
</details>
