<!--------------------------------------
   SCREEN SHOT
--------------------------------------->
<table>
<tr>
<td>
<font size="3"><b>isANONpapers</b></font>
<br>
<img src="screenshot.png" width=90%>
</td>
<td>
<details>
<summary><b>isANONpapers</b> (description)</summary>
<b>isANONpapers</b> is NOT a table, but the list of papers the work plan says will be written: every category, task or
subtask whose title starts with <i>Paper N:</i> (for example <i>Paper 1: Deep imaging of faint stellar halos</i>; any
capitals, any spaces) is paper N, with the rest of the title as the paper's title. Because the papers are known by the
number you give them, not by their place in the plan, adding or moving tasks never changes which paper is which.
In your document, <code>\papertitle{1}</code> prints paper 1's title anywhere (in the text, a heading, a caption), and
<code>\listplannedpapers</code> lists the papers in number order: <i>Paper 1: title</i>, <i>Paper 2: title</i> ...
</details>
</td>
</tr>
</table>
<hr>

<!--------------------------------------
   HOW TO USE
--------------------------------------->
<b>HOW TO USE:</b>

<!-- - - - - - - - - - - - - - - - - - - - - - - - - - - -
             Special Packages
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -->
<details>
<summary><b>Load worpt.sty</b> [<i>one-time-only task</i> for inclusion of any/all WorPT files]</summary>
Add this line to the preamble of your document, as the last package loaded (after aastex, xcolor, hyperref and the rest). It loads only the few packages the WorPT tables need, and skips any your document has already loaded.
<pre><code>
\usepackage{worpt}
</code></pre>
worpt.sty reads isANONpapers.tex by itself at <code>\begin{document}</code>, so <code>\papertitle</code> needs nothing else.
</details>

<!-- - - - - - - - - - - - - - - - - - - - - - - - - - - -
             Paper titles in the text
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -->
<details>
<summary><b>A paper's title in the text</b></summary>
Write <code>\papertitle{N}</code> wherever paper N's title should appear, for example:
<pre><code>
The results of Task A1.1 will be published in Paper~1, \textit{\papertitle{1}}.
</code></pre>
<ul>
<li>The title is the work plan's, so it is always the current one: change the task's title in WorPT and the document follows at its next compile.</li>
<li>A number with no paper (a mistyped number, or a paper taken out of the work plan) prints a bold <b>??</b>, and the LaTeX log says "There is no Paper N in the work plan".</li>
<li>AASTeX makes section headings capitals letter by letter, which a command's text escapes: in a heading, write <code>\MakeUppercase{\papertitle{1}}</code> to have the title in capitals too.</li>
<li>WorPT warns (on the dashboard, its Tables tab and in gooTeX's log) when two items are titled with the same paper number (the first in the plan keeps the number) or when a "Paper N:" has no title after it. Numbers need not follow on from each other: Paper 1, Paper 2, Paper 5 is fine.</li>
</ul>
</details>

<!-- - - - - - - - - - - - - - - - - - - - - - - - - - - -
             Putting File Contents Into Document
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -->
<details>
<summary><mark><b>How To Put the List Into Your Document</b></mark> [<i>one-time-only task for inclusion of this file</i>]</summary>
<ol>
<li>COPY the lines in the code block below, then</li>
<li>PASTE into your document WHERE you want the list of papers to appear.</li>
</ol>
Refer to <b>Customizations</b> section below to add personal preferences in the gap between the \input and \listplannedpapers lines below.

<pre><code>
%:::::::::::::::::: start isANONpapers ::::::::::::::::::::
\input{isANONpapers} % the papers planned in the work plan
\listplannedpapers
%::::::::::::::::::: end isANONpapers :::::::::::::::::::::
</code></pre>

</details>

<!-- - - - - - - - - - - - - - - - - - - - - - - - - - - -
             Customizations
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -->
<details>
<summary><b>Customize appearance</b> [<i>do as many times as needed</i>]</summary>
COPY any of the lines below (they show the default values), PASTE them into your document, either in the preamble after <code>\usepackage{worpt}</code> or <b>between</b> the \input and \listplannedpapers lines, and EDIT them there. <i>Highlights show what can be edited.</i>

<table>

<tr>
<td><b>The list of papers</b></td>
<td><pre><code>
\def\PlannedPaperLabel#1{<mark>\textbf{Paper~#1:}</mark>}   % the label in front of each paper (#1 is its number)
\def\PlannedPaperFormat#1{<mark>#1</mark>}                  % each title in the list (e.g. \textit{#1})
\def\PlannedPapersSpace{<mark>\itemsep</mark>}               % space between papers in the list (a length, e.g. 2pt)
\def\NoPlannedPapersText{<mark>\textbf{??} (no planned papers: the work plan has no tasks titled ``Paper N: title'')</mark>}
</code></pre>
The titles line up after the widest label, and a long title wraps under its own first line. When the work plan has no papers yet, the list is <code>\NoPlannedPapersText</code> instead, and the LaTeX log says so.</td>
</tr>

</table>
</details>

<!--------------------------------------
   NUCLEAR OPTION
--------------------------------------->
<details>
<summary><b>NUCLEAR OPTION</b> <i>[when nothing else works]</i></summary>
If you just cannot get the list to look like you want it to look, you can write your own list in your document, using <code>\papertitle{1}</code>, <code>\papertitle{2}</code> ... for the titles, so they still come from the work plan.
</details>
