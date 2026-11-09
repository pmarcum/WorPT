<!--------------------------------------
   SCREEN SHOT
--------------------------------------->
<table>
<tr>
<td>
<font size="3"><b>NOTANONtasks</b></font>
<br>
<img src="https://lh3.googleusercontent.com/d/12BO4XZpEwodyHwtDSvcrKBhmCwkxysLS" width=70%>
</td>
<td>
<details>
<summary><b>NOTANONtasks</b> (description)</summary>
<b>NOTANONtasks</b> is a table of project tasks, organized under task categories, as specified by the TASKS page in the
WorPT spreadsheet. The task lead and team members assisting with each task are specified as well. No
level-of-effort information is given in this table, only tasks and assignments to illustrate team member involvement. 
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
Add this line to the preamble of your document, as the last package loaded (after aastex, xcolor, hyperref and the rest). It loads only the few packages the WorPT tables need, and skips any your document has already loaded. The file <code>worpt.sty</code> comes with the tables (see https://github.com/pmarcum/WorPT/blob/main/latexTableTemplates/WorPTpackages for more info).
<pre><code>
\usepackage{worpt}
</code></pre>
</details>

<!-- - - - - - - - - - - - - - - - - - - - - - - - - - - - 
             Putting File Contents Into Document
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -->
<details>
<summary><mark><b>How To Put File Contents Into Your Document</b></mark> [<i>one-time-only task for inclusion of this file</i>]</summary> 
<ol>
<li>COPY the lines in the code block below, then</li>
<li>PASTE into your document WHERE you want the content to appear, then</li>
<li>MODIFY the editable lines you just pasted in your document as needed. The lines that may be edited (or even deleted altogether if not wanted) are indicated by highlight below. </li><br>
Refer to <b>Customizations</b> section below to add personal preferences in the gap between \input and \begin{NOTANONtasks} lines below.

</ol>
    
<pre><code>
%::::::::::::::::::: start NOTANONtasks :::::::::::::::::::
%\clearpage                                          % [optional] (could instead use \newpage, or comment out)
\input{NOTANONtasks} % reset file parameters

\begin{NOTANONtasks}
\caption{\normalsize\textbf{Task Management and Team Responsibilities}:\\
The tasks (gray headers) and sub-tasks (left), with specific assignments for the roles of task lead (middle) and expertise / analysis assistance (right).} \label{tab:NOTANONtasks}
\end{NOTANONtasks}
%::::::::::::::::::: end NOTANONtasks :::::::::::::::::::::
</code></pre>

</details>

<!-- - - - - - - - - - - - - - - - - - - - - - - - - - - - 
             Customizations
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -->
<details>
<summary><b>Customize appearance</b> [<i>do as many times as needed</i>]</summary 
You can change column widths, column alignment, colors, font style using additional lines that are copy/pasted into your document. Specifically: 
<ol>
<li>COPY any or all lines in the code block below that are related to the formatting parameter that you want to edit. The lines below show default values. You will edit those values to make desired changes.</li>
<li>PASTE the copied lines into your document into the gap <b>between</b> the \input and \begin{NOTANONtasks} lines. </li>
<li>EDIT the pasted lines in your document, as desired. Some examples are given at the bottom of this page.</li>
NOTE: you can PICK AND CHOOSE the lines you want to paste into your document; you do not have to copy/paste all of the beow lines!
</ol>

<!-- . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . .
                              Options   
<!-- . . . . . . . . . . . . . . . . . . . . . . . . . . . . . . -->
<table>

<tr>
<td><b>Table orientation</b></td>
<td><pre><code>
\LandScapetrue          % will put the table in landscape mode
</code></pre>
Without this line, the table is set in landscape mode only when it needs to be: when the "Tasks" column would be narrower than <code>\MinTitleWidth</code> (below).
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/16SbKRxlDHWshgzt-tQNsjqqSOJeCXWm1" width=15%>
</details>
</td>
</tr>

<tr>
<td><b>Column width adjustments</b></td>
<td><pre><code>
\def\MinTitleWidth{<mark>1.5in</mark>}        % narrowest "Tasks" column before switching to landscape mode
\def\LeadWidth{<mark>1.2in</mark>}            % middle ("Lead") column width
\def\ExpertiseWidth{<mark>1.8in</mark>}       % rightmost ("Expertise") column width
\def\TaskWidth{<mark>3.9in</mark>}            % leftmost ("Tasks") column width (leave this line out to use what is left)
</code></pre>
The table is always as wide as the page's text; in a two-column document it spans both columns. The "Tasks" column gets the width the other columns leave, unless you give it a width here. Each task's label and title stay on one line: a title too long for the "Tasks" column is cut short at a word, with "...", and so does a category's, in its banner across the table. Give the task or category a short title in WorPT to choose what shows.
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1Lc84Ce7q9vDGbn-PSkLpHm3Bk-018GLC" width=50%>
</details>
</td>
</tr>

<tr>
<td><b>Table compactness</b></td>
<td><pre><code>
\def\SpaceBetweenRows{<mark>0.8</mark>}    % vertical compactness of rows
\def\SpaceBetweenColumns{<mark>1pt</mark>} % bigger = wider spacing between columns
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1BgsQCk-CpfftDKheaAs1wfUg7jO7UDAB" width=50%>
</details>
</td>
</tr>

<tr>
<td><b>Column label color and font style</b></td>
<td>
For fontstyle changes, the "\textbf" can be changed to "\emph" for italics, or can
be turned into plain test by removing the "\textbf", eg {{#1}}
<pre><code>
\def\HeaderColor{<mark>Blue</mark>}            % column heading color
\def\HeaderFontColor{<mark>White</mark>}       % column heading font color
\def\HeaderFontstyle#1{<mark>\textbf</mark>{#1}}% boldface column heading labels
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1rpXA2Cuw9_19nElBYJPs79SEU8fNTMgT" width=50%>
</details>
</td>
</tr>

<tr>
<td><b>Color and font style of category banners</b></td>
<td><pre><code>
\def\SectionColor{<mark>gray!40</mark>}       % category section label colors
\def\SectionFontColor{<mark>Black</mark>}     % category section label font color
\def\SectionFontstyle#1{<mark>\textbf</mark>{#1}} % boldface category section labels
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1l2e9IXnIq7Zewg3RfBfrQ_SXUr9FtLy1" width=50%>
</details>
</td>
</tr>

<tr>
<td><b>Color of faint vertical line</b></td>
<td><pre><code>
\def\VerticalLineColor{<mark>gray!40</mark>}  % color of line between "Lead" and "Expertise"
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1ZyFAQkPU5ifcHN4pSln1KSeHaLu5VGWq" width=50%>
</details>
</td>
</tr>

<tr>
<td><b>Table columns - full control</b></td>
<td>
For more control over the table's layout (removing or adding vertical lines, changing column alignment, etc.), copy the
ENTIRE code below into your document after the table's <code>\input</code> line, and change it there.<br>
<u>IMPORTANT</u> keep the number of columns (any <code>p</code> that is removed must be replaced by another column type). You may keep the width settings (like <code>\TaskWidth</code>) and set them as shown above, or write widths in their place.
<pre><code>
\def\NOTANONtasksColumns{
  <mark>|>{\leavevmode}p{\TaskWidth}||</mark>                                % title column
  <mark>>{\leavevmode}p{\LeadWidth}!{\color{\VerticalLineColor}\vrule}</mark>% line bet Lead/Expertise
  <mark>>{\leavevmode}p{\ExpertiseWidth}|</mark>                             % Expertise column
}
</code></pre></td>
</tr>
</table>
</details>

<!--------------------------------------
   EXAMPLES 
--------------------------------------->
<details>
<summary><b>Examples</b></summary>
The below is an example of how one can change the appearance of the contents within a LaTeX document. Yellow highlights note the preferences that were changed, and yellow highlight in the rendered file/table indicate the changes related to preferences. 
     
<img src="https://lh3.googleusercontent.com/d/1JaLRe1Et6Ap4g--A7tGZg7aey46fFeN6" width=60%>

NOTE: To return to default values, all I have to do is comment-out (put a "%" at the line's beginning) the "\def" formatting lines that I pasted. 
</details>

<!--------------------------------------
   NUCLEAR OPTION 
--------------------------------------->
<details>
<summary><b>NUCLEAR OPTION</b> <i>[when nothing else works]</i></summary>
If you just cannot get the table to look like you want it to look, you can always copy/paste the entire NOTANONtasks.tex file that appears in the WorPT subfolder, into your document, and then edit at-will.  Some of the WorPT files involve complicated LaTeX code, so be sure that you have a good mastery of LaTeX and know what you are doing before implementing this option!
</details>
