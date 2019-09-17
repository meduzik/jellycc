%{
  extern int yylex();}
%}
%option noyywrap
%%
alignas  {acc++;}
alignof  {acc++;}
and  {acc++;}
and_eq  {acc++;}
asm  {acc++;}
atomic_cancel  {acc++;}
atomic_commit  {acc++;}
atomic_noexcept  {acc++;}
auto  {acc++;}
bitand  {acc++;}
bitor  {acc++;}
bool  {acc++;}
break  {acc++;}
case  {acc++;}
catch  {acc++;}
char  {acc++;}
char8_t  {acc++;}
char16_t  {acc++;}
char32_t  {acc++;}
class  {acc++;}
compl  {acc++;}
concept  {acc++;}
const  {acc++;}
consteval  {acc++;}
constexpr  {acc++;}
const_cast  {acc++;}
continue  {acc++;}
co_await  {acc++;}
co_return  {acc++;}
co_yield  {acc++;}
decltype  {acc++;}
default  {acc++;}
delete  {acc++;}
do  {acc++;}
double  {acc++;}
dynamic_cast  {acc++;}
else  {acc++;}
enum  {acc++;}
explicit  {acc++;}
export  {acc++;}
extern  {acc++;}
false  {acc++;}
float  {acc++;}
for  {acc++;}
friend  {acc++;}
goto  {acc++;}
if  {acc++;}
inline  {acc++;}
int  {acc++;}
long  {acc++;}
mutable  {acc++;}
namespace  {acc++;}
new  {acc++;}
noexcept  {acc++;}
not  {acc++;}
not_eq  {acc++;}
nullptr  {acc++;}
operator  {acc++;}
or  {acc++;}
or_eq  {acc++;}
private  {acc++;}
protected  {acc++;}
public  {acc++;}
reflexpr  {acc++;}
register  {acc++;}
reinterpret_cast  {acc++;}
requires  {acc++;}
return  {acc++;}
short  {acc++;}
signed  {acc++;}
sizeof  {acc++;}
static  {acc++;}
static_assert  {acc++;}
static_cast  {acc++;}
struct  {acc++;}
switch  {acc++;}
synchronized  {acc++;}
template  {acc++;}
this  {acc++;}
thread_local  {acc++;}
throw  {acc++;}
true  {acc++;}
try  {acc++;}
typedef  {acc++;}
typeid  {acc++;}
typename  {acc++;}
union  {acc++;}
unsigned  {acc++;}
using  {acc++;}
virtual  {acc++;}
void  {acc++;}
volatile  {acc++;}
wchar_t  {acc++;}
while  {acc++;}
xor  {acc++;}
xor_eq   {acc++;}

[a-zA-Z_][a-zA-Z0-9_]  {acc++;}

(0|[1-9][0-9]*)  {acc++;}
(0|[1-9][0-9]*)[.][0-9]+([eE][+\-]?[0-9]+)?  {acc++;}
0x[0-9a-fA-F]+  {acc++;}
0b[01]+  {acc++;}

"//"[^\n\r]+(\n|\r|\r\n)?  {acc++;}
"/*"([^*]|[*]*[^/*])*[*]*"*/"  {acc++;}

\"(\\[nrt0\\"]|\\x[0-9a-fA-F]{2}|[^"\\])*\"  {acc++;}
\'(\\[nrt0\\"]|\\x[0-9a-fA-F]{2}|[^"\\])\'  {acc++;}

"("  {acc++;}
")"  {acc++;}
"["  {acc++;}
"]"  {acc++;}
"{"  {acc++;}
"}"  {acc++;}

"#"  {acc++;}

"="  {acc++;}
"+="  {acc++;}
"-="  {acc++;}
"*="  {acc++;}
"/="  {acc++;}
"%="  {acc++;}
"&="  {acc++;}
"|="  {acc++;}
"^="  {acc++;}
"<<="  {acc++;}
">>="  {acc++;}

"++"  {acc++;}
"--"  {acc++;}

"+"  {acc++;}
"-"  {acc++;}
"*"  {acc++;}
"/"  {acc++;}
"%"  {acc++;}
"~"  {acc++;}
"&"  {acc++;}
"|"  {acc++;}
"||"  {acc++;}
"&&"  {acc++;}
"^"  {acc++;}
"<<"  {acc++;}
">>"  {acc++;}

"=="  {acc++;}
"!="  {acc++;}
"<"  {acc++;}
">"  {acc++;}
"<="  {acc++;}
">="  {acc++;}

"->"  {acc++;}
"."  {acc++;}
","  {acc++;}
":"  {acc++;}
";"  {acc++;}
"?"  {acc++;}

(" "|\r\n|\n|\r|\t)+  {acc++;}

. {acc++;}

%%
