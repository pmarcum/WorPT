<!--------------------------------------
   SCREEN SHOT
--------------------------------------->
<table>
<tr>
<td>
<font size="3"><b>NOTANONhst</b></font>
<br>
<img src="https://lh3.googleusercontent.com/d/1OpijauwkFzgEorqyUsArZlkZz6ZcB__d" width=70%>
</td>
<td>
<details>
<summary><b>NOTANONhst</b> (description)</summary>
<b>NOTANONhst</b> is a tabulated summary of team member roles, following the format for HST Phase II proposals.  The table lists each team member, their relationship to the project (PI, co-I, etc.), their institutional affiliation and whether or not the institution is U.S.-based, and a brief narrative summary of their role on the project. The table also indicates if the team member is funded or unfunded through the proposal, and what their total level of work effort (in FTE) is.
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
Refer to <b>Customizations</b> section below to add personal preferences in the gap between \input and \begin{NOTANONhst} lines below.
</ol>
   
<pre><code>
%:::::::::::::::::::: start NOTANONhst ::::::::::::::::::::::
\input{NOTANONhst} % reset file parameters
\def\ProgramID{HST-xx-xxxxx (Cycle XX)} % fill in details

\begin{NOTANONhst}
\caption{\textbf{Work Effort for All Members}\hspace{1em} Team members, identified by their name and role in the proposed project, are listed with their institutional affiliation and position, with a "F" or "US" indicating foreign or U.S. institution. A brief narrative of their role in the project is given.  A 'Y' or 'N' indicates if the person is funded by the proposed budget or not, respectively.  The total work-effort of the team member, summed over full life of the proposed  project, is in the rightmost column (multiply displayed FTE value by 12 to get work effort in number of months units).}
\label{tab:NOTANONhst}
\end{NOTANONhst}
%::::::::::::::::::::: end NOTANONhst :::::::::::::::::::::::
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
<li>PASTE the copied lines into your document into the gap <b>between</b> the \def\ProgramID and \begin{NOTANONhst} lines. </li>
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
<td><b>Column width adjustments</b></td>
<td><pre><code>
\def\ContributorWidth{<mark>1.8in</mark>}      % Contributor column width
\def\PositionWidth{<mark>1.3in</mark>}         % Position column width
\def\FundedMemberWidth{<mark>0.22in</mark>}    % Funded(?) column width
\def\FteWidth{<mark>0.42in</mark>}             % FTE column width
\def\RoleWidth{<mark>2.5in</mark>}             % Role column width (leave this line out to use what is left)
</code></pre>
The table is always as wide as the page's text; in a two-column document it spans both columns. The Role column gets the width the other columns leave, unless you give it a width here.
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1VFoxre2-539OyEXfklTvudu-PYBlPuaJ" width=70%>
</details>
</td>
</tr>
    
<tr>
<td><b>Table compactness</b></td>
<td><pre><code>
\def\SpaceBetweenRows{<mark>1</mark>}      % vertical compactness of rows
\def\SpaceBetweenColumns{<mark>1pt</mark>} % bigger = wider spacing between columns
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1XhVrw4lR70_WbosdIZ7x-mowtJRTPVqs" width=50%>
</details>
</td>
</tr>

<tr>
<td><b>Column label color and font style</b></td>
<td>
For fontstyle changes, the "\textbf" can be changed to "\emph" for italics, or can be turned into plain test by removing the "\textbf", eg {{#1}}
<pre><code>
\def\HeaderColor{<mark>Blue</mark>}             % column heading color
\def\LabelColor{<mark>White</mark>}             % column heading font color
\def\LabelFontstyle#1{<mark>\textbf</mark>{#1}} % boldface column label
\def\VerticalLineColor{<mark>lightgray</mark>}  % color of vertical lines
</code></pre>
<details>
<summary>reference image</summary>
<img src="https://lh3.googleusercontent.com/d/1VlOwoxQeP8kprw-Ua_XleCuhklszXV7Z" width=50%>
</details>
</td>
</tr>

<tr>
<td><b>Table columns - full control</b></td>
<td>
For more control over the table's layout (removing or adding vertical lines, changing column alignment, etc.), copy the
ENTIRE code below into your document after the table's <code>\input</code> line, and change it there.<br>
<u>IMPORTANT</u> keep the number of columns (any <code>p</code> that is removed must be replaced by another column type). You may keep the width settings (like <code>\ContributorWidth</code>) and set them as shown above, or write widths in their place.
<pre><code>
\def\NOTANONhstColumns{
<mark>|>{\raggedright\let\newline\\\arraybackslash\hspace{0pt}}p{\ContributorWidth}!{\color{\VerticalLineColor}\vrule}</mark> % Contributor column
<mark>>{\raggedright\let\newline\\\arraybackslash\hspace{0pt}}p{\PositionWidth}!{\color{\VerticalLineColor}\vrule}</mark>     % Position column
<mark>>{\raggedright\let\newline\\\arraybackslash\hspace{0pt}}p{\RoleWidth}!{\color{\VerticalLineColor}\vrule}</mark>         % Role column
<mark>p{\FundedMemberWidth}!{\color{\VerticalLineColor}\vrule}</mark> % Funded(?) column
<mark>p{\FteWidth}|</mark>                                            % FTE column
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
   
 <img src="https://lh3.googleusercontent.com/d/1QOff63_b8AUEFpRMKUlaGK0LcEz3NvCK" width=50%>

NOTE: To return to default values, all I have to do is comment-out (put a "%" at the line's beginning) the "\def" formatting lines that I pasted. 
</details>

<!--------------------------------------
   NUCLEAR OPTION 
--------------------------------------->
<details>
<summary><b>NUCLEAR OPTION</b> <i>[when nothing else works]</i></summary>
If you just cannot get the table to look like you want it to look, you can always copy/paste the entire NOTANONhst.tex file that appears in the WorPT subfolder, into your document, and then edit at-will.  Some of the WorPT files involve complicated LaTeX code, so be sure that you have a good mastery of LaTeX and know what you are doing before implementing this option!
</details>
