<!--------------------------------------
   SCREEN SHOT
--------------------------------------->
<table>
<tr>
<td>
<font size="3"><b>NOTANONschedule</b></font>
<br>
<img src="https://lh3.googleusercontent.com/d/1rdPPWxa8nlGOFGYbZyQ6Frq9zj01w4Ww" width=75%>
</td>
<td>
<details>
<summary><b>NOTANONschedule</b> (description)</summary>
<b>NOTANONschedule</b> is a resource-loaded project schedule showing project tasks with their timelines, and a column for each team member marking who leads each task and who works on it (funded by this grant, or partly or wholly unfunded). The table gives each task's total work effort, and each team member's funded and unfunded effort over the whole grant. Institutional affiliation (U.S. or international) is also indicated. The information in this table comes from the work plan in WorPT.
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
Refer to <b>Customizations</b> section below to add personal preferences in the gap between \input and \begin{NOTANONschedule} lines below.

</ol>
   
<pre><code>
%::::::::::::::::: start NOTANONschedule :::::::::::::::::::
%\clearpage         % [optional] (could instead use \newpage, or comment out)
\input{NOTANONschedule} % reset file parameters

\begin{NOTANONschedule}
\caption{Resource-loaded project schedule. Tasks are listed (left side), with duration of task activity indicated in blue-colored timelines, in months, under quarter-year labels (1,2,3,4); a task with subtasks (indented below it) has a light blue timeline spanning theirs. Each team member has a column (label color: blue$=$funded/U.S., black$=$not funded/U.S., red$=$international), marked for each task they work on: \TeamLeadKey$=$task lead, \TeamFundedKey$=$funded by this grant, \TeamUnfundedKey$=$partly or wholly not funded by this grant. The bottom rows give each team member's funded and unfunded effort over the whole grant in FTE (1~FTE$=$12~months); ``Total FTE'' (right side) is each task's effort, funded and unfunded: in italics for a task with subtasks (theirs added up), and in bold for a task category (its tasks added up).}
\label{tab:NOTANONschedule}
\end{NOTANONschedule}
%:::::::::::::::::: end NOTANONschedule ::::::::::::::::::::
</code></pre>

</details>

<!-- - - - - - - - - - - - - - - - - - - - - - - - - - - - 
             Customizations
- - - - - - - - - - - - - - - - - - - - - - - - - - - - -->
<details>
<summary><b>Customize appearance</b> [<i>do as many times as needed</i>]</summary>
You can change column widths, column alignment, colors, font style using additional lines that are copy/pasted into your document. Specifically: 
<ol>
<li>COPY any or all lines in the code block below that are related to the formatting parameter that you want to edit. The lines below show default values. You will edit those values to make desired changes.</li>
<li>PASTE the copied lines into your document into the gap <b>between</b> the \input and \begin{NOTANONschedule} lines. </li>
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
Without this line, the table is set in landscape mode only when it needs to be: when the title column would be narrower than <code>\MinTitleWidth</code> (below).
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/16SbKRxlDHWshgzt-tQNsjqqSOJeCXWm1" width=15%>
</details>
</td>
</tr>

<tr>
<td><b>Column width adjustments</b></td>
<td><pre><code>
\def\MinTitleWidth{<mark>1.5in</mark>}   % narrowest title column before switching to landscape mode
\def\TimelineWidth{<mark>0.6ex</mark>}   % skinny timeline columns width (one per month)
\def\TeamCellPadding{<mark>1pt</mark>}   % room beside the sideways label and numbers in a team member's column
</code></pre>
The table is always as wide as the page's text. Each team member's column is just wide enough for its label and the numbers at its foot, both printed sideways (plus <code>\TeamCellPadding</code>); a smaller font for them makes the columns narrower. The Total FTE column is as wide as its numbers, with its label sideways. The title column gets the width that is left. A title too long for it is cut short at a word, with "...": give the task a short title in WorPT to choose what shows. The month columns are made wider than <code>\TimelineWidth</code> if the timeline's labels need it.
</td>
</tr>

<tr>
<td><b>Column label font adjustments</b></td>
<td><pre><code>
\def\TaskTimelineHeaderFontsize{<mark>\scriptsize</mark>}   % Task Timeline label text size
\def\TeamHeaderFontsize{<mark>\scriptsize</mark>}           % Team label text size
\def\TotalFteHeaderFontsize{<mark>\scriptsize</mark>}       % Total FTE label text size (printed sideways)
\def\YearHeaderFontsize{<mark>\scriptsize</mark>}           % "YEAR1", "YEAR2"... label text size
\def\TaskTitleHeaderFontsize{<mark>\normalsize</mark>}      % "TASK TITLES" column label text size
\def\YearSliceHeaderFontsize{<mark>\scriptsize</mark>}      % "1", "2"... year-quarter label text size
</code></pre>
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
<img src="https://lh3.googleusercontent.com/d/1wgKhN-aCTVc2Vi6bJ8FAyoZrK3f8SNfA" width=65%>
</details></td>
</tr>

<tr>
<td><b>CATEGORY, TASK label row entry formatting</b></td>
<td>
For fontstyle changes, the "\textbf" can be changed to "\emph" for italics, or can<br>
be turned into plain test by removing the "\textbf" or other formatting. You do 
need to keep the #1 and #2 references. For example, if you just want plain text, you could
redefine as:<br>
\def\TaskCategoryLabel#1#2{{#1}~{#2}}
<pre><code>
\def\TaskCategoryLabel#1#2{{<mark>\normalsize\textbf</mark>{#1}}~
   {<mark>\normalsize\textbf</mark>{#2}}}                               % Category label
\def\TaskTitleLabel#1#2{~{<mark>\scriptsize{\textbf</mark>{#1}}}~
   {<mark>\color{mediumelectricblue}{\footnotesize\textbf</mark>{#2}}}} % Task title format for row item
\def\SubtaskIndent{<mark>1em</mark>}                             % how far a subtask's title is indented
\def\SubtaskTitleLabel#1#2{\hspace{\SubtaskIndent}\TaskTitleLabel{#1}{#2}} % Subtask title format
</code></pre>
For italic subtask titles, for example: <code>\def\SubtaskTitleLabel#1#2{\hspace{\SubtaskIndent}{\itshape\TaskTitleLabel{#1}{#2}}}</code>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1FptrYPilkvMpYVCh0EHQX5cKxFiZXUFh" width=50%>
</details>
</td>
</tr>

<tr>
<td><b>Vertical line colors</b></td>
<td><pre><code>
\def\TimelineVerticalLineColor{<mark>lightgray</mark>}   % lines between quarters in the timeline
\def\TimelineMonthLineColor{<mark>lightgray!45</mark>}   % lines between months, fainter
\def\TeamVerticalLineColor{<mark>lightgray</mark>}       % lines between team members
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1AewnKa1OXlrgT4bNIqy3JrVWkqW4lcYR" width=50%>
</details></td>
</tr>

<tr>
<td><b>Color of task timelines</b></td>
<td><pre><code>
\def\TimelineColor{<mark>mediumelectricblue</mark>}   % Task Timeline cell color (a task, or a subtask)
\def\ParentTimelineColor{<mark>mediumelectricblue!35</mark>} % a task that has subtasks (its timeline spans theirs)
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/12H_J3b7oNhnd9ZDHivqEkQ2gdAJl8hWV" width=50%>
</details></td>
</tr>

<tr>
<td><b>Team members' column labels: institution and funding</b></td>
<td><pre><code>
\def\FundedUsTeam#1{<mark>\small \color{blue}</mark>{#1}}    % funded US team member's label
\def\UnfundedUsTeam#1{<mark>\small \color{black}</mark>{#1}} % unfunded US team member's label
\def\InternationalTeam#1{<mark>\small \color{red}</mark>{#1}}% international team member's label
</code></pre>
The labels are printed sideways, above each team member's column.
</td>
</tr>

<tr>
<td><b>Marks for who leads and who works on each task</b></td>
<td><pre><code>
\def\TeamLeadColor{<mark>black</mark>}       % task lead: a solid mark
\def\TeamFundedColor{<mark>gray!65</mark>}   % works on the task, funded by this grant: a solid mark
\def\TeamUnfundedColor{<mark>gray!80</mark>} % works on the task, some or all of it not funded by this grant: an open box
\def\TeamOutline{<mark>0.6pt</mark>}         % the open box's line
</code></pre>
A task lead is marked in the lead color whether or not their work on it is funded. The caption shows the three marks with <code>\TeamLeadKey</code>, <code>\TeamFundedKey</code> and <code>\TeamUnfundedKey</code>.
</td>
</tr>

<tr>
<td><b>FTE values</b></td>
<td><pre><code>
\def\FteTotalFormat#1{<mark>\small</mark>{#1}}                       % a task's (or subtask's) own Total FTE (right)
\def\FteRolledUpFormat#1{<mark>\small\itshape\color{mediumelectricblue}</mark>{#1}} % a task with subtasks: theirs, added up
\def\FteCategoryFormat#1{<mark>\small\bfseries</mark>{#1}}            % a task category: its tasks', added up
\def\FteGrandTotalFormat#1{<mark>\small\bfseries</mark>{#1}}          % the whole team's funded and unfunded FTE (foot)
\def\TeamFundedFteFormat#1{<mark>\scriptsize\color{blue}</mark>{#1}} % a team member's funded FTE (foot)
\def\TeamUnfundedFteFormat#1{<mark>\scriptsize</mark>{#1}}           % a team member's unfunded FTE (foot)
\def\TeamZeroFteFormat#1{<mark>\scriptsize\color{lightgray}</mark>{#1}} % a team member's FTE when it is zero
\def\TeamFundedFteLabel{<mark>\scriptsize\textbf{Funded FTE}</mark>}     % label of the foot's funded row
\def\TeamUnfundedFteLabel{<mark>\scriptsize\textbf{Unfunded FTE}</mark>} % label of the foot's unfunded row
</code></pre>
The two rows at the foot give each team member's funded and unfunded effort over the whole grant, printed sideways; their Total FTE cells give the whole team's.
</td>
</tr>

<tr>
<td><b>Team members' names in the caption (optional)</b></td>
<td>
The suggested caption leaves the team members' names out: their labels are roles (PI, Sci-PI, co-I 1...), which keeps the
table anonymous. To name them, add <code>Team member identities: \RevealIdentities.</code> to your caption; each is set as
<pre><code>
\def\RevealIdentityFormat#1#2{<mark>\textbf</mark>{#1}<mark>: </mark>#2} % \#1=label, \#2=name
</code></pre>
</td>
</tr>

<tr>
<td><b>Table columns - full control</b></td>
<td>
For more control over the table's layout (removing or adding vertical lines, changing column alignment, etc.), copy the
ENTIRE code below into your document after the table's <code>\input</code> line, and change it there.<br>
<u>IMPORTANT</u> keep the number of columns, <code>\NumberYears</code>, <code>\NumberTeamMinusOne</code>, <code>\WorPTtitleWidth</code>, <code>\WorPTmonthWidth</code>, <code>\WorPTteamWidth</code> and <code>\WorPTfteWidth</code> (WorPT works these out).
<pre><code>
\def\NOTANONscheduleColumns{%
<mark>|>{\raggedright\arraybackslash\leavevmode}p{\WorPTtitleWidth}</mark>% title column
<mark>|*{\NumberYears}{@{}</mark>%                                      timeline: a column per month
<mark>p{\WorPTmonthWidth}@{\MonthRule}p{\WorPTmonthWidth}@{\MonthRule}p{\WorPTmonthWidth}@{\QuarterRule}</mark>%
<mark>p{\WorPTmonthWidth}@{\MonthRule}p{\WorPTmonthWidth}@{\MonthRule}p{\WorPTmonthWidth}@{\QuarterRule}</mark>%
<mark>p{\WorPTmonthWidth}@{\MonthRule}p{\WorPTmonthWidth}@{\MonthRule}p{\WorPTmonthWidth}@{\QuarterRule}</mark>%
<mark>p{\WorPTmonthWidth}@{\MonthRule}p{\WorPTmonthWidth}@{\MonthRule}p{\WorPTmonthWidth}@{}|}</mark>%
<mark>@{}*{\NumberTeamMinusOne}{>{\centering\arraybackslash\leavevmode}p{\WorPTteamWidth}@{\TeamRule}}</mark>% team: a column per member
<mark>>{\centering\arraybackslash\leavevmode}p{\WorPTteamWidth}@{}</mark>%
<mark>|>{\centering\arraybackslash\leavevmode}p{\WorPTfteWidth}|</mark>%    total fte column
}
</code></pre>
(aastex and revtex misread a repeat inside a repeat, or a repeat that starts with <code>|</code> then <code>@</code>: keep the timeline and team columns written this way.)</td>

</table>
</details>

<!--------------------------------------
   EXAMPLES 
--------------------------------------->
<details>
<summary><b>Examples</b></summary>
The below is an example of how one can change the appearance of the contents within a LaTeX document. Yellow highlights note the preferences that were changed, and yellow highlight in the rendered file/table indicate the changes related to preferences. 
      
<img src="https://lh3.googleusercontent.com/d/1Fj0juT0UURcvBU8PaYDLYMuC4OVmdJCk" width=60%>

NOTE: To return to default values, all I have to do is comment-out (put a "%" at the line's beginning) the "\def" formatting lines that I pasted. 
</details>

<!--------------------------------------
   NUCLEAR OPTION 
--------------------------------------->
<details>
<summary><b>NUCLEAR OPTION</b> <i>[when nothing else works]</i></summary>
If you just cannot get the table to look like you want it to look, you can always copy/paste the entire NOTANONschedule.tex file that appears in the WorPT subfolder, into your document, and then edit at-will.  Some of the WorPT files involve complicated LaTeX code, so be sure that you have a good mastery of LaTeX and know what you are doing before implementing this option!
</details>
