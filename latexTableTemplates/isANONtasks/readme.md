<!--------------------------------------
   SCREEN SHOT
--------------------------------------->
<table>
<tr>
<td>
<font size="3"><b>isANONtasks</b></font>
<br>
<img src="https://lh3.googleusercontent.com/d/1gfMagfSDmX0lDqzAmel2LCGZTuZUGQ5O" width=80%>
</td>
<td>
<details>
<summary><b>isANONtasks</b> (description)</summary>
<b>isANONtasks</b> is a table of project tasks, organized under task categories, as specified by the TASKS page in the WorPT spreadsheet. The task lead and team members (identified not by name but by project role) assisting with each task are specified as well. No level-of-effort information is given in this table, only tasks and assignments to illustrate team member involvement, as well as start and finish timeline information for each task.
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
Refer to <b>Customizations</b> section below to add personal preferences in the gap between \input and \begin{isANONtasks} lines below.

</ol>
   
<pre><code>
%::::::::::::::::::: start isANONtasks :::::::::::::::::::::
\input{isANONtasks}  % reset file parameters

\begin{isANONtasks}
\caption{\textbf{Task Timeline:} Team member roles, rightmost column, are cross-referenced with corresponding names in the non-anonymized personnel and work effort table. {\color{red}[Describe the planned papers and other products, e.g. \textbf{Paper~1:} \ldots; \textbf{Paper~2:} \ldots]}}
\label{tab:isANONtasks}
\end{isANONtasks}
%::::::::::::::::::: end isANONtasks ::::::::::::::::::::::
</code></pre>

</details>

<!-- - - - - - - - - - - - - - - - - - - - - - - - - - - - 
             Customizations
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -->
<details>
<summary><b>Customize appearance</b> [<i>do as many times as needed</i>]</summary>
The default table appearance is already optimized, minimizing the need to change table properties such as column widths. However, if you do find the need to make such changes, as well as changes to other properties such as column alignment, colors, font styles, you will need to copy/paste and then edit some additional formatting lines into your document. Specifically:
<ol>
<li>COPY any or all lines in the code block below that are related to the formatting parameter that you want to edit. The lines below show default values. You will edit those values to make desired changes.</li>
<li>PASTE the copied lines into your document into the gap <b>between</b> the \input and \begin{isANONtasks} lines. </li>
<li>EDIT the pasted lines in your document, as desired.</li>
NOTE: THe lines are grouped into categories to help you locate what you need. You can PICK AND CHOOSE the lines you want to paste into your document; you do not have to copy/paste all of the lines below (unless noted) and do not have to copy all lines within a group.<br>
<i>Highlights indicate what parts of the commands can be edited without breaking your LaTeX code.</i><br>
You can just comment out your added lines and recompile the document, if you want to return to default values.
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
Without this line, the table is set in landscape mode only when it needs to be: when the "Task" column would be narrower than <code>\MinTitleWidth</code> (below).
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1vMs3teKHoqZGHGqHZj4HrtaZZp9Xq0Xa" width=20%>
</details>
</td>
</tr>

<tr>
<td><b>Column width adjustments</b></td>
<td><pre><code>
\def\MinTitleWidth{<mark>1in</mark>}     % narrowest "Task" column before switching to landscape mode
\def\StartFinishWidth{<mark>0.2in</mark>} % width of start/finish columns
\def\LeadWidth{<mark>0.5in</mark>}        % width of "Task Lead" column
\def\ExpertiseWidth{<mark>1.5in</mark>}   % width of rightmost ("Expertise") column
\def\TaskWidth{<mark>3.4in</mark>}        % width of leftmost ("Task") column (leave this line out to use what is left)
</code></pre>
The table is always as wide as the page's text; in a two-column document it spans both columns. The "Task" column gets the width the other columns leave, unless you give it a width here; a long title takes more than one line.
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/13oCZxeIfopxwB6SfXjmThW4JepSNconJ" width=60%>
</details>
</td>
</tr>

<tr>
<td><b>Table compactness</b></td>
<td><pre><code>
\def\SpaceBetweenRows{<mark>0.87</mark>}    % vertical compactness of rows
\def\SpaceBetweenColumns{<mark>2pt</mark>} % bigger = wider spacing between columns
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/16uvtXkaEDCZRso5eqzBA3Y3NKo4rjphn" width=60%>
</details>
</td>
</tr>

<tr>
<td><b>Color and font style of category banners</b></td>
<td><pre><code>
\def\SectionColor{<mark>Blue</mark>}              % category section label colors
\def\SectionFontColor{<mark>White</mark>}         % category title font color
\def\SectionFontstyle#1{<mark>\textbf</mark>{#1}} % boldface category title
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1gxJcyUbm5iVLsKrsxrynn-wuqp7-YgnU" width=60%>
</details>
</td>
</tr>

<tr>
<td><b>Color and font style of column headers</b></td>
<td><pre><code>
\def\ColumnLabelFontstyle#1{<mark>\textbf</mark>{#1}}  % boldface all the column headers
\def\YearFontColor{<mark>Red</mark>}                   % font color under "Y" (year) columns in Start/Finish
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1FyRgEblao5yAiiuGxC78IHeV6m9k3843" width=60%>
</details>
</td>
</tr>

<tr>
<td><b>Color of faint vertical line</b></td>
<td><pre><code>
\def\YearQuarterLineColor{<mark>lightgray</mark>}      % vertical line color in year/quarter Start/Finish columns
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1LHdvupXYjQmpvncz-UxbGuyjAjdidLnY" width=60%>
</details>
</td>
</tr>

<tr>
<td><b>Table columns - full control</b></td>
<td>
For more control over the table's layout (removing or adding vertical lines, changing column alignment, etc.), copy the
ENTIRE code below into your document after the table's <code>\input</code> line, and change it there.<br>
<u>IMPORTANT</u> keep the number of columns (any column type that is removed must be replaced by another). You may keep the settings (like <code>\TaskWidth</code>) and set them as shown above, or write values in their place.
<pre><code>
\def\isANONtasksColumns{
  <mark>|>{\leavevmode}p{\TaskWidth}||</mark>       % title column
  <mark>>{\leavevmode}p{\StartFinishWidth}!{\color{\YearQuarterLineColor}\vrule}</mark> % Start/year
  <mark>>{\leavevmode}p{\StartFinishWidth}!{\color{\YearQuarterLineColor}\vrule}!{\color{\YearQuarterLineColor}\vrule}</mark> % Start/quarter
  <mark>>{\leavevmode}p{\StartFinishWidth}!{\color{\YearQuarterLineColor}\vrule}</mark> % Finish/year
  <mark>>{\leavevmode}p{\StartFinishWidth}||</mark> % Finish/quarter
  <mark>>{\leavevmode}p{\LeadWidth}!{\color{\YearQuarterLineColor}\vrule}</mark> % Task Lead column
  <mark>>{\leavevmode}p{\ExpertiseWidth}|</mark>    % Expertise column
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
   
<img src="https://lh3.googleusercontent.com/d/11h84W4PCBE_a9TruZ6TXbafv7afOQFQk" width=60%>

NOTE: To return to default values, all I have to do is comment-out (put a "%" at the line's beginning) the "\def" formatting lines that I pasted. 
</details>

<!--------------------------------------
   NUCLEAR OPTION 
--------------------------------------->
<details>
<summary><b>NUCLEAR OPTION</b> <i>[when nothing else works]</i></summary>
If you just cannot get the table to look like you want it to look, you can always copy/paste the entire isANONtasks.tex file that appears in the WorPT subfolder, into your document, and then edit at-will.  Some of the WorPT files involve complicated LaTeX code, so be sure that you have a good mastery of LaTeX and know what you are doing before implementing this option!
</details>
