// A Bison parser, made by GNU Bison 3.4.

// Skeleton implementation for Bison LALR(1) parsers in C++

// Copyright (C) 2002-2015, 2018-2019 Free Software Foundation, Inc.

// This program is free software: you can redistribute it and/or modify
// it under the terms of the GNU General Public License as published by
// the Free Software Foundation, either version 3 of the License, or
// (at your option) any later version.

// This program is distributed in the hope that it will be useful,
// but WITHOUT ANY WARRANTY; without even the implied warranty of
// MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
// GNU General Public License for more details.

// You should have received a copy of the GNU General Public License
// along with this program.  If not, see <http://www.gnu.org/licenses/>.

// As a special exception, you may create a larger work that contains
// part or all of the Bison parser skeleton and distribute that work
// under terms of your choice, so long as that work isn't itself a
// parser generator using the skeleton or a modified version thereof
// as a parser skeleton.  Alternatively, if you modify or redistribute
// the parser skeleton itself, you may (at your option) remove this
// special exception, which will cause the skeleton and the resulting
// Bison output files to be licensed under the GNU General Public
// License without this special exception.

// This special exception was added by the Free Software Foundation in
// version 2.2 of Bison.

// Undocumented macros, especially those whose name start with YY_,
// are private implementation details.  Do not rely on them.


// Take the name prefix into account.
#define yylex   VerilogParserlex

// First part of user prologue.
#line 4 "VerilogParser.yy"
 /*** C/C++ Declarations ***/

#include <stdio.h>
#include <string>
#include <vector>


#line 50 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"


#include "VerilogParser.h"

// Second part of user prologue.
#line 117 "VerilogParser.yy"


#include "VerilogDriver.h"
#include "VerilogScanner.h"

/* this "connects" the bison parser in the driver to the flex scanner class
 * object. it defines the yylex() function call to pull the next token from the
 * current lexer object of the driver context. */
#undef yylex
#define yylex driver.lexer->lex


#line 69 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"



#ifndef YY_
# if defined YYENABLE_NLS && YYENABLE_NLS
#  if ENABLE_NLS
#   include <libintl.h> // FIXME: INFRINGES ON USER NAME SPACE.
#   define YY_(msgid) dgettext ("bison-runtime", msgid)
#  endif
# endif
# ifndef YY_
#  define YY_(msgid) msgid
# endif
#endif

// Whether we are compiled with exception support.
#ifndef YY_EXCEPTIONS
# if defined __GNUC__ && !defined __EXCEPTIONS
#  define YY_EXCEPTIONS 0
# else
#  define YY_EXCEPTIONS 1
# endif
#endif

#define YYRHSLOC(Rhs, K) ((Rhs)[K].location)
/* YYLLOC_DEFAULT -- Set CURRENT to span from RHS[1] to RHS[N].
   If N is 0, then set CURRENT to the empty location which ends
   the previous symbol: RHS[0] (always defined).  */

# ifndef YYLLOC_DEFAULT
#  define YYLLOC_DEFAULT(Current, Rhs, N)                               \
    do                                                                  \
      if (N)                                                            \
        {                                                               \
          (Current).begin  = YYRHSLOC (Rhs, 1).begin;                   \
          (Current).end    = YYRHSLOC (Rhs, N).end;                     \
        }                                                               \
      else                                                              \
        {                                                               \
          (Current).begin = (Current).end = YYRHSLOC (Rhs, 0).end;      \
        }                                                               \
    while (false)
# endif


// Suppress unused-variable warnings by "using" E.
#define YYUSE(E) ((void) (E))

// Enable debugging if requested.
#if VERILOGPARSERDEBUG

// A pseudo ostream that takes yydebug_ into account.
# define YYCDEBUG if (yydebug_) (*yycdebug_)

# define YY_SYMBOL_PRINT(Title, Symbol)         \
  do {                                          \
    if (yydebug_)                               \
    {                                           \
      *yycdebug_ << Title << ' ';               \
      yy_print_ (*yycdebug_, Symbol);           \
      *yycdebug_ << '\n';                       \
    }                                           \
  } while (false)

# define YY_REDUCE_PRINT(Rule)          \
  do {                                  \
    if (yydebug_)                       \
      yy_reduce_print_ (Rule);          \
  } while (false)

# define YY_STACK_PRINT()               \
  do {                                  \
    if (yydebug_)                       \
      yystack_print_ ();                \
  } while (false)

#else // !VERILOGPARSERDEBUG

# define YYCDEBUG if (false) std::cerr
# define YY_SYMBOL_PRINT(Title, Symbol)  YYUSE (Symbol)
# define YY_REDUCE_PRINT(Rule)           static_cast<void> (0)
# define YY_STACK_PRINT()                static_cast<void> (0)

#endif // !VERILOGPARSERDEBUG

#define yyerrok         (yyerrstatus_ = 0)
#define yyclearin       (yyla.clear ())

#define YYACCEPT        goto yyacceptlab
#define YYABORT         goto yyabortlab
#define YYERROR         goto yyerrorlab
#define YYRECOVERING()  (!!yyerrstatus_)

namespace VerilogParser {
#line 164 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"


  /* Return YYSTR after stripping away unnecessary quotes and
     backslashes, so that it's suitable for yyerror.  The heuristic is
     that double-quoting is unnecessary unless the string contains an
     apostrophe, a comma, or backslash (other than backslash-backslash).
     YYSTR is taken from yytname.  */
  std::string
  Parser::yytnamerr_ (const char *yystr)
  {
    if (*yystr == '"')
      {
        std::string yyr;
        char const *yyp = yystr;

        for (;;)
          switch (*++yyp)
            {
            case '\'':
            case ',':
              goto do_not_strip_quotes;

            case '\\':
              if (*++yyp != '\\')
                goto do_not_strip_quotes;
              else
                goto append;

            append:
            default:
              yyr += *yyp;
              break;

            case '"':
              return yyr;
            }
      do_not_strip_quotes: ;
      }

    return yystr;
  }


  /// Build a parser object.
  Parser::Parser (class Driver& driver_yyarg)
    :
#if VERILOGPARSERDEBUG
      yydebug_ (false),
      yycdebug_ (&std::cerr),
#endif
      driver (driver_yyarg)
  {}

  Parser::~Parser ()
  {}

  Parser::syntax_error::~syntax_error () YY_NOEXCEPT YY_NOTHROW
  {}

  /*---------------.
  | Symbol types.  |
  `---------------*/

  // basic_symbol.
#if 201103L <= YY_CPLUSPLUS
  template <typename Base>
  Parser::basic_symbol<Base>::basic_symbol (basic_symbol&& that)
    : Base (std::move (that))
    , value (std::move (that.value))
    , location (std::move (that.location))
  {}
#endif

  template <typename Base>
  Parser::basic_symbol<Base>::basic_symbol (const basic_symbol& that)
    : Base (that)
    , value (that.value)
    , location (that.location)
  {}


  /// Constructor for valueless symbols.
  template <typename Base>
  Parser::basic_symbol<Base>::basic_symbol (typename Base::kind_type t, YY_MOVE_REF (location_type) l)
    : Base (t)
    , value ()
    , location (l)
  {}

  template <typename Base>
  Parser::basic_symbol<Base>::basic_symbol (typename Base::kind_type t, YY_RVREF (semantic_type) v, YY_RVREF (location_type) l)
    : Base (t)
    , value (YY_MOVE (v))
    , location (YY_MOVE (l))
  {}

  template <typename Base>
  bool
  Parser::basic_symbol<Base>::empty () const YY_NOEXCEPT
  {
    return Base::type_get () == empty_symbol;
  }

  template <typename Base>
  void
  Parser::basic_symbol<Base>::move (basic_symbol& s)
  {
    super_type::move (s);
    value = YY_MOVE (s.value);
    location = YY_MOVE (s.location);
  }

  // by_type.
  Parser::by_type::by_type ()
    : type (empty_symbol)
  {}

#if 201103L <= YY_CPLUSPLUS
  Parser::by_type::by_type (by_type&& that)
    : type (that.type)
  {
    that.clear ();
  }
#endif

  Parser::by_type::by_type (const by_type& that)
    : type (that.type)
  {}

  Parser::by_type::by_type (token_type t)
    : type (yytranslate_ (t))
  {}

  void
  Parser::by_type::clear ()
  {
    type = empty_symbol;
  }

  void
  Parser::by_type::move (by_type& that)
  {
    type = that.type;
    that.clear ();
  }

  int
  Parser::by_type::type_get () const YY_NOEXCEPT
  {
    return type;
  }


  // by_state.
  Parser::by_state::by_state () YY_NOEXCEPT
    : state (empty_state)
  {}

  Parser::by_state::by_state (const by_state& that) YY_NOEXCEPT
    : state (that.state)
  {}

  void
  Parser::by_state::clear () YY_NOEXCEPT
  {
    state = empty_state;
  }

  void
  Parser::by_state::move (by_state& that)
  {
    state = that.state;
    that.clear ();
  }

  Parser::by_state::by_state (state_type s) YY_NOEXCEPT
    : state (s)
  {}

  Parser::symbol_number_type
  Parser::by_state::type_get () const YY_NOEXCEPT
  {
    if (state == empty_state)
      return empty_symbol;
    else
      return yystos_[state];
  }

  Parser::stack_symbol_type::stack_symbol_type ()
  {}

  Parser::stack_symbol_type::stack_symbol_type (YY_RVREF (stack_symbol_type) that)
    : super_type (YY_MOVE (that.state), YY_MOVE (that.value), YY_MOVE (that.location))
  {
#if 201103L <= YY_CPLUSPLUS
    // that is emptied.
    that.state = empty_state;
#endif
  }

  Parser::stack_symbol_type::stack_symbol_type (state_type s, YY_MOVE_REF (symbol_type) that)
    : super_type (s, YY_MOVE (that.value), YY_MOVE (that.location))
  {
    // that is emptied.
    that.type = empty_symbol;
  }

#if YY_CPLUSPLUS < 201103L
  Parser::stack_symbol_type&
  Parser::stack_symbol_type::operator= (stack_symbol_type& that)
  {
    state = that.state;
    value = that.value;
    location = that.location;
    // that is emptied.
    that.state = empty_state;
    return *this;
  }
#endif

  template <typename Base>
  void
  Parser::yy_destroy_ (const char* yymsg, basic_symbol<Base>& yysym) const
  {
    if (yymsg)
      YY_SYMBOL_PRINT (yymsg, yysym);

    // User destructor.
    switch (yysym.type_get ())
    {
      case 14: // NAME
#line 110 "VerilogParser.yy"
        {delete (yysym.value.stringVal);}
#line 398 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
        break;

      case 42: // range
#line 111 "VerilogParser.yy"
        {delete (yysym.value.rangeVal);}
#line 404 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
        break;

      case 43: // general_name_array
#line 113 "VerilogParser.yy"
        {delete (yysym.value.generalNameArrayVal);}
#line 410 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
        break;

      default:
        break;
    }
  }

#if VERILOGPARSERDEBUG
  template <typename Base>
  void
  Parser::yy_print_ (std::ostream& yyo,
                                     const basic_symbol<Base>& yysym) const
  {
    std::ostream& yyoutput = yyo;
    YYUSE (yyoutput);
    symbol_number_type yytype = yysym.type_get ();
#if defined __GNUC__ && ! defined __clang__ && ! defined __ICC && __GNUC__ * 100 + __GNUC_MINOR__ <= 408
    // Avoid a (spurious) G++ 4.8 warning about "array subscript is
    // below array bounds".
    if (yysym.empty ())
      std::abort ();
#endif
    yyo << (yytype < yyntokens_ ? "token" : "nterm")
        << ' ' << yytname_[yytype] << " ("
        << yysym.location << ": ";
    YYUSE (yytype);
    yyo << ')';
  }
#endif

  void
  Parser::yypush_ (const char* m, YY_MOVE_REF (stack_symbol_type) sym)
  {
    if (m)
      YY_SYMBOL_PRINT (m, sym);
    yystack_.push (YY_MOVE (sym));
  }

  void
  Parser::yypush_ (const char* m, state_type s, YY_MOVE_REF (symbol_type) sym)
  {
#if 201103L <= YY_CPLUSPLUS
    yypush_ (m, stack_symbol_type (s, std::move (sym)));
#else
    stack_symbol_type ss (s, sym);
    yypush_ (m, ss);
#endif
  }

  void
  Parser::yypop_ (int n)
  {
    yystack_.pop (n);
  }

#if VERILOGPARSERDEBUG
  std::ostream&
  Parser::debug_stream () const
  {
    return *yycdebug_;
  }

  void
  Parser::set_debug_stream (std::ostream& o)
  {
    yycdebug_ = &o;
  }


  Parser::debug_level_type
  Parser::debug_level () const
  {
    return yydebug_;
  }

  void
  Parser::set_debug_level (debug_level_type l)
  {
    yydebug_ = l;
  }
#endif // VERILOGPARSERDEBUG

  Parser::state_type
  Parser::yy_lr_goto_state_ (state_type yystate, int yysym)
  {
    int yyr = yypgoto_[yysym - yyntokens_] + yystate;
    if (0 <= yyr && yyr <= yylast_ && yycheck_[yyr] == yystate)
      return yytable_[yyr];
    else
      return yydefgoto_[yysym - yyntokens_];
  }

  bool
  Parser::yy_pact_value_is_default_ (int yyvalue)
  {
    return yyvalue == yypact_ninf_;
  }

  bool
  Parser::yy_table_value_is_error_ (int yyvalue)
  {
    return yyvalue == yytable_ninf_;
  }

  int
  Parser::operator() ()
  {
    return parse ();
  }

  int
  Parser::parse ()
  {
    // State.
    int yyn;
    /// Length of the RHS of the rule being reduced.
    int yylen = 0;

    // Error handling.
    int yynerrs_ = 0;
    int yyerrstatus_ = 0;

    /// The lookahead symbol.
    symbol_type yyla;

    /// The locations where the error started and ended.
    stack_symbol_type yyerror_range[3];

    /// The return value of parse ().
    int yyresult;

#if YY_EXCEPTIONS
    try
#endif // YY_EXCEPTIONS
      {
    YYCDEBUG << "Starting parse\n";


    // User initialization code.
#line 39 "VerilogParser.yy"
{
    // initialize the initial location object
    yyla.location.begin.filename = yyla.location.end.filename = &driver.streamname;
}

#line 556 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"


    /* Initialize the stack.  The initial state will be set in
       yynewstate, since the latter expects the semantical and the
       location values to have been already stored, initialize these
       stacks with a primary value.  */
    yystack_.clear ();
    yypush_ (YY_NULLPTR, 0, YY_MOVE (yyla));

  /*-----------------------------------------------.
  | yynewstate -- push a new symbol on the stack.  |
  `-----------------------------------------------*/
  yynewstate:
    YYCDEBUG << "Entering state " << yystack_[0].state << '\n';

    // Accept?
    if (yystack_[0].state == yyfinal_)
      YYACCEPT;

    goto yybackup;


  /*-----------.
  | yybackup.  |
  `-----------*/
  yybackup:
    // Try to take a decision without lookahead.
    yyn = yypact_[yystack_[0].state];
    if (yy_pact_value_is_default_ (yyn))
      goto yydefault;

    // Read a lookahead token.
    if (yyla.empty ())
      {
        YYCDEBUG << "Reading a token: ";
#if YY_EXCEPTIONS
        try
#endif // YY_EXCEPTIONS
          {
            yyla.type = yytranslate_ (yylex (&yyla.value, &yyla.location));
          }
#if YY_EXCEPTIONS
        catch (const syntax_error& yyexc)
          {
            YYCDEBUG << "Caught exception: " << yyexc.what() << '\n';
            error (yyexc);
            goto yyerrlab1;
          }
#endif // YY_EXCEPTIONS
      }
    YY_SYMBOL_PRINT ("Next token is", yyla);

    /* If the proper action on seeing token YYLA.TYPE is to reduce or
       to detect an error, take that action.  */
    yyn += yyla.type_get ();
    if (yyn < 0 || yylast_ < yyn || yycheck_[yyn] != yyla.type_get ())
      goto yydefault;

    // Reduce or error.
    yyn = yytable_[yyn];
    if (yyn <= 0)
      {
        if (yy_table_value_is_error_ (yyn))
          goto yyerrlab;
        yyn = -yyn;
        goto yyreduce;
      }

    // Count tokens shifted since error; after three, turn off error status.
    if (yyerrstatus_)
      --yyerrstatus_;

    // Shift the lookahead token.
    yypush_ ("Shifting", yyn, YY_MOVE (yyla));
    goto yynewstate;


  /*-----------------------------------------------------------.
  | yydefault -- do the default action for the current state.  |
  `-----------------------------------------------------------*/
  yydefault:
    yyn = yydefact_[yystack_[0].state];
    if (yyn == 0)
      goto yyerrlab;
    goto yyreduce;


  /*-----------------------------.
  | yyreduce -- do a reduction.  |
  `-----------------------------*/
  yyreduce:
    yylen = yyr2_[yyn];
    {
      stack_symbol_type yylhs;
      yylhs.state = yy_lr_goto_state_ (yystack_[yylen].state, yyr1_[yyn]);
      /* If YYLEN is nonzero, implement the default value of the
         action: '$$ = $1'.  Otherwise, use the top of the stack.

         Otherwise, the following line sets YYLHS.VALUE to garbage.
         This behavior is undocumented and Bison users should not rely
         upon it.  */
      if (yylen)
        yylhs.value = yystack_[yylen - 1].value;
      else
        yylhs.value = yystack_[0].value;

      // Default location.
      {
        stack_type::slice range (yystack_, yylen);
        YYLLOC_DEFAULT (yylhs.location, range, yylen);
        yyerror_range[1].location = yylhs.location;
      }

      // Perform the reduction.
      YY_REDUCE_PRINT (yyn);
#if YY_EXCEPTIONS
      try
#endif // YY_EXCEPTIONS
        {
          switch (yyn)
            {
  case 2:
#line 134 "VerilogParser.yy"
    {(yylhs.value.rangeVal) = new Range ((yystack_[3].value.integerVal), (yystack_[1].value.integerVal));}
#line 681 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 3:
#line 135 "VerilogParser.yy"
    {(yylhs.value.rangeVal) = new Range (std::numeric_limits<int>::min(), (yystack_[1].value.integerVal));}
#line 687 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 4:
#line 152 "VerilogParser.yy"
    {
          (yylhs.value.generalNameArrayVal) = new GeneralNameArray(1, GeneralName(*(yystack_[0].value.stringVal)));
          delete (yystack_[0].value.stringVal);
        }
#line 696 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 5:
#line 156 "VerilogParser.yy"
    {
          (yylhs.value.generalNameArrayVal) = new GeneralNameArray(1, GeneralName(*(yystack_[1].value.stringVal), (yystack_[0].value.rangeVal)->low, (yystack_[0].value.rangeVal)->high));
          delete (yystack_[1].value.stringVal);
          delete (yystack_[0].value.rangeVal); 
        }
#line 706 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 6:
#line 161 "VerilogParser.yy"
    {
            (yystack_[2].value.generalNameArrayVal)->push_back(GeneralName(*(yystack_[0].value.stringVal)));
            delete (yystack_[0].value.stringVal);
            (yylhs.value.generalNameArrayVal) = (yystack_[2].value.generalNameArrayVal);
        }
#line 716 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 7:
#line 166 "VerilogParser.yy"
    {
            (yystack_[3].value.generalNameArrayVal)->push_back(GeneralName(*(yystack_[1].value.stringVal), (yystack_[0].value.rangeVal)->low, (yystack_[0].value.rangeVal)->high));
            delete (yystack_[1].value.stringVal);
            delete (yystack_[0].value.rangeVal); 
            (yylhs.value.generalNameArrayVal) = (yystack_[3].value.generalNameArrayVal);
        }
#line 727 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 8:
#line 180 "VerilogParser.yy"
    {driver.wire_pin_cbk(*(yystack_[1].value.stringVal), *(yystack_[3].value.stringVal)); delete (yystack_[3].value.stringVal); delete (yystack_[1].value.stringVal);}
#line 733 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 9:
#line 181 "VerilogParser.yy"
    {driver.wire_pin_cbk(*(yystack_[2].value.stringVal), *(yystack_[4].value.stringVal), *(yystack_[1].value.rangeVal)); delete (yystack_[4].value.stringVal); delete (yystack_[2].value.stringVal); delete (yystack_[1].value.rangeVal);}
#line 739 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 10:
#line 182 "VerilogParser.yy"
    {delete (yystack_[2].value.stringVal);}
#line 745 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 11:
#line 183 "VerilogParser.yy"
    {driver.wire_pin_cbk((yystack_[1].value.mask).bits, (yystack_[1].value.mask).value, *(yystack_[3].value.stringVal)); delete (yystack_[3].value.stringVal);}
#line 751 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 12:
#line 184 "VerilogParser.yy"
    {driver.wire_pin_cbk((yystack_[1].value.mask).bits, (yystack_[1].value.mask).value, *(yystack_[3].value.stringVal)); delete (yystack_[3].value.stringVal);}
#line 757 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 13:
#line 185 "VerilogParser.yy"
    {driver.wire_pin_cbk((yystack_[1].value.mask).bits, (yystack_[1].value.mask).value, *(yystack_[3].value.stringVal)); delete (yystack_[3].value.stringVal);}
#line 763 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 14:
#line 186 "VerilogParser.yy"
    {driver.wire_pin_cbk((yystack_[1].value.mask).bits, (yystack_[1].value.mask).value, *(yystack_[3].value.stringVal)); delete (yystack_[3].value.stringVal);}
#line 769 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 15:
#line 187 "VerilogParser.yy"
    {driver.wire_pin_cbk(*(yystack_[2].value.generalNameArrayVal), *(yystack_[5].value.stringVal)); delete (yystack_[5].value.stringVal); delete (yystack_[2].value.generalNameArrayVal);}
#line 775 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 16:
#line 190 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kINPUT); delete (yystack_[0].value.generalNameArrayVal);}
#line 781 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 17:
#line 191 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kINPUT, *(yystack_[1].value.rangeVal)); delete (yystack_[1].value.rangeVal); delete (yystack_[0].value.generalNameArrayVal);}
#line 787 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 18:
#line 192 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kINPUT|kREG, *(yystack_[1].value.rangeVal)); delete (yystack_[1].value.rangeVal); delete (yystack_[0].value.generalNameArrayVal);}
#line 793 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 19:
#line 193 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kINPUT|kREG); delete (yystack_[0].value.generalNameArrayVal);}
#line 799 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 20:
#line 194 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kOUTPUT); delete (yystack_[0].value.generalNameArrayVal);}
#line 805 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 21:
#line 195 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kOUTPUT, *(yystack_[1].value.rangeVal)); delete (yystack_[1].value.rangeVal); delete (yystack_[0].value.generalNameArrayVal);}
#line 811 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 22:
#line 196 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kOUTPUT|kREG, *(yystack_[1].value.rangeVal)); delete (yystack_[1].value.rangeVal); delete (yystack_[0].value.generalNameArrayVal);}
#line 817 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 23:
#line 197 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kOUTPUT|kREG); delete (yystack_[0].value.generalNameArrayVal);}
#line 823 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 24:
#line 198 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kINPUT|kOUTPUT); delete (yystack_[0].value.generalNameArrayVal);}
#line 829 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 25:
#line 199 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kINPUT|kOUTPUT, *(yystack_[1].value.rangeVal)); delete (yystack_[1].value.rangeVal); delete (yystack_[0].value.generalNameArrayVal);}
#line 835 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 26:
#line 200 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kINPUT|kOUTPUT|kREG, *(yystack_[1].value.rangeVal)); delete (yystack_[1].value.rangeVal); delete (yystack_[0].value.generalNameArrayVal);}
#line 841 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 27:
#line 201 "VerilogParser.yy"
    {driver.pin_declare_cbk(*(yystack_[0].value.generalNameArrayVal), kINPUT|kOUTPUT|kREG); delete (yystack_[0].value.generalNameArrayVal);}
#line 847 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 28:
#line 204 "VerilogParser.yy"
    {delete (yystack_[0].value.generalNameArrayVal);}
#line 853 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 29:
#line 205 "VerilogParser.yy"
    {delete (yystack_[1].value.rangeVal); delete (yystack_[0].value.generalNameArrayVal);}
#line 859 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 30:
#line 208 "VerilogParser.yy"
    {driver.wire_declare_cbk(*(yystack_[0].value.generalNameArrayVal)); delete (yystack_[0].value.generalNameArrayVal);}
#line 865 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 31:
#line 209 "VerilogParser.yy"
    {driver.wire_declare_cbk(*(yystack_[0].value.generalNameArrayVal), *(yystack_[1].value.rangeVal)); delete (yystack_[1].value.rangeVal); delete (yystack_[0].value.generalNameArrayVal);}
#line 871 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 32:
#line 225 "VerilogParser.yy"
    {driver.module_name_cbk(*(yystack_[3].value.stringVal), GeneralNameArray()); delete (yystack_[3].value.stringVal);}
#line 877 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 33:
#line 226 "VerilogParser.yy"
    {driver.module_name_cbk(*(yystack_[4].value.stringVal), *(yystack_[2].value.generalNameArrayVal)); delete (yystack_[4].value.stringVal); delete (yystack_[2].value.generalNameArrayVal);}
#line 883 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 40:
#line 240 "VerilogParser.yy"
    {driver.module_instance_cbk(*(yystack_[5].value.stringVal), *(yystack_[4].value.stringVal)); delete (yystack_[5].value.stringVal); delete (yystack_[4].value.stringVal);}
#line 889 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 41:
#line 241 "VerilogParser.yy"
    {
               /* append NUM to instance name */
               char buf[256];
               sprintf(buf, "[%d]", (yystack_[5].value.integerVal));
               (yystack_[7].value.stringVal)->append(buf);
               driver.module_instance_cbk(*(yystack_[8].value.stringVal), *(yystack_[7].value.stringVal)); 
               delete (yystack_[8].value.stringVal); 
               delete (yystack_[7].value.stringVal);
               }
#line 903 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 42:
#line 252 "VerilogParser.yy"
    {driver.assignment_cbk(*(yystack_[3].value.stringVal), Range(), *(yystack_[1].value.stringVal), Range()); delete (yystack_[3].value.stringVal); delete (yystack_[1].value.stringVal);}
#line 909 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 43:
#line 253 "VerilogParser.yy"
    {driver.assignment_cbk(*(yystack_[4].value.stringVal), *(yystack_[3].value.rangeVal), *(yystack_[1].value.stringVal), Range()); delete (yystack_[4].value.stringVal); delete (yystack_[3].value.rangeVal); delete (yystack_[1].value.stringVal);}
#line 915 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 44:
#line 254 "VerilogParser.yy"
    {driver.assignment_cbk(*(yystack_[4].value.stringVal), Range(), *(yystack_[2].value.stringVal), *(yystack_[1].value.rangeVal)); delete (yystack_[4].value.stringVal); delete (yystack_[2].value.stringVal); delete (yystack_[1].value.rangeVal);}
#line 921 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;

  case 45:
#line 255 "VerilogParser.yy"
    {driver.assignment_cbk(*(yystack_[5].value.stringVal), *(yystack_[4].value.rangeVal), *(yystack_[2].value.stringVal), *(yystack_[1].value.rangeVal)); delete (yystack_[5].value.stringVal); delete (yystack_[4].value.rangeVal); delete (yystack_[2].value.stringVal); delete (yystack_[1].value.rangeVal);}
#line 927 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"
    break;


#line 931 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"

            default:
              break;
            }
        }
#if YY_EXCEPTIONS
      catch (const syntax_error& yyexc)
        {
          YYCDEBUG << "Caught exception: " << yyexc.what() << '\n';
          error (yyexc);
          YYERROR;
        }
#endif // YY_EXCEPTIONS
      YY_SYMBOL_PRINT ("-> $$ =", yylhs);
      yypop_ (yylen);
      yylen = 0;
      YY_STACK_PRINT ();

      // Shift the result of the reduction.
      yypush_ (YY_NULLPTR, YY_MOVE (yylhs));
    }
    goto yynewstate;


  /*--------------------------------------.
  | yyerrlab -- here on detecting error.  |
  `--------------------------------------*/
  yyerrlab:
    // If not already recovering from an error, report this error.
    if (!yyerrstatus_)
      {
        ++yynerrs_;
        error (yyla.location, yysyntax_error_ (yystack_[0].state, yyla));
      }


    yyerror_range[1].location = yyla.location;
    if (yyerrstatus_ == 3)
      {
        /* If just tried and failed to reuse lookahead token after an
           error, discard it.  */

        // Return failure if at end of input.
        if (yyla.type_get () == yyeof_)
          YYABORT;
        else if (!yyla.empty ())
          {
            yy_destroy_ ("Error: discarding", yyla);
            yyla.clear ();
          }
      }

    // Else will try to reuse lookahead token after shifting the error token.
    goto yyerrlab1;


  /*---------------------------------------------------.
  | yyerrorlab -- error raised explicitly by YYERROR.  |
  `---------------------------------------------------*/
  yyerrorlab:
    /* Pacify compilers when the user code never invokes YYERROR and
       the label yyerrorlab therefore never appears in user code.  */
    if (false)
      YYERROR;

    /* Do not reclaim the symbols of the rule whose action triggered
       this YYERROR.  */
    yypop_ (yylen);
    yylen = 0;
    goto yyerrlab1;


  /*-------------------------------------------------------------.
  | yyerrlab1 -- common code for both syntax error and YYERROR.  |
  `-------------------------------------------------------------*/
  yyerrlab1:
    yyerrstatus_ = 3;   // Each real token shifted decrements this.
    {
      stack_symbol_type error_token;
      for (;;)
        {
          yyn = yypact_[yystack_[0].state];
          if (!yy_pact_value_is_default_ (yyn))
            {
              yyn += yyterror_;
              if (0 <= yyn && yyn <= yylast_ && yycheck_[yyn] == yyterror_)
                {
                  yyn = yytable_[yyn];
                  if (0 < yyn)
                    break;
                }
            }

          // Pop the current state because it cannot handle the error token.
          if (yystack_.size () == 1)
            YYABORT;

          yyerror_range[1].location = yystack_[0].location;
          yy_destroy_ ("Error: popping", yystack_[0]);
          yypop_ ();
          YY_STACK_PRINT ();
        }

      yyerror_range[2].location = yyla.location;
      YYLLOC_DEFAULT (error_token.location, yyerror_range, 2);

      // Shift the error token.
      error_token.state = yyn;
      yypush_ ("Shifting", YY_MOVE (error_token));
    }
    goto yynewstate;


  /*-------------------------------------.
  | yyacceptlab -- YYACCEPT comes here.  |
  `-------------------------------------*/
  yyacceptlab:
    yyresult = 0;
    goto yyreturn;


  /*-----------------------------------.
  | yyabortlab -- YYABORT comes here.  |
  `-----------------------------------*/
  yyabortlab:
    yyresult = 1;
    goto yyreturn;


  /*-----------------------------------------------------.
  | yyreturn -- parsing is finished, return the result.  |
  `-----------------------------------------------------*/
  yyreturn:
    if (!yyla.empty ())
      yy_destroy_ ("Cleanup: discarding lookahead", yyla);

    /* Do not reclaim the symbols of the rule whose action triggered
       this YYABORT or YYACCEPT.  */
    yypop_ (yylen);
    while (1 < yystack_.size ())
      {
        yy_destroy_ ("Cleanup: popping", yystack_[0]);
        yypop_ ();
      }

    return yyresult;
  }
#if YY_EXCEPTIONS
    catch (...)
      {
        YYCDEBUG << "Exception caught: cleaning lookahead and stack\n";
        // Do not try to display the values of the reclaimed symbols,
        // as their printers might throw an exception.
        if (!yyla.empty ())
          yy_destroy_ (YY_NULLPTR, yyla);

        while (1 < yystack_.size ())
          {
            yy_destroy_ (YY_NULLPTR, yystack_[0]);
            yypop_ ();
          }
        throw;
      }
#endif // YY_EXCEPTIONS
  }

  void
  Parser::error (const syntax_error& yyexc)
  {
    error (yyexc.location, yyexc.what ());
  }

  // Generate an error message.
  std::string
  Parser::yysyntax_error_ (state_type yystate, const symbol_type& yyla) const
  {
    // Number of reported tokens (one for the "unexpected", one per
    // "expected").
    size_t yycount = 0;
    // Its maximum.
    enum { YYERROR_VERBOSE_ARGS_MAXIMUM = 5 };
    // Arguments of yyformat.
    char const *yyarg[YYERROR_VERBOSE_ARGS_MAXIMUM];

    /* There are many possibilities here to consider:
       - If this state is a consistent state with a default action, then
         the only way this function was invoked is if the default action
         is an error action.  In that case, don't check for expected
         tokens because there are none.
       - The only way there can be no lookahead present (in yyla) is
         if this state is a consistent state with a default action.
         Thus, detecting the absence of a lookahead is sufficient to
         determine that there is no unexpected or expected token to
         report.  In that case, just report a simple "syntax error".
       - Don't assume there isn't a lookahead just because this state is
         a consistent state with a default action.  There might have
         been a previous inconsistent state, consistent state with a
         non-default action, or user semantic action that manipulated
         yyla.  (However, yyla is currently not documented for users.)
       - Of course, the expected token list depends on states to have
         correct lookahead information, and it depends on the parser not
         to perform extra reductions after fetching a lookahead from the
         scanner and before detecting a syntax error.  Thus, state
         merging (from LALR or IELR) and default reductions corrupt the
         expected token list.  However, the list is correct for
         canonical LR with one exception: it will still contain any
         token that will not be accepted due to an error action in a
         later state.
    */
    if (!yyla.empty ())
      {
        int yytoken = yyla.type_get ();
        yyarg[yycount++] = yytname_[yytoken];
        int yyn = yypact_[yystate];
        if (!yy_pact_value_is_default_ (yyn))
          {
            /* Start YYX at -YYN if negative to avoid negative indexes in
               YYCHECK.  In other words, skip the first -YYN actions for
               this state because they are default actions.  */
            int yyxbegin = yyn < 0 ? -yyn : 0;
            // Stay within bounds of both yycheck and yytname.
            int yychecklim = yylast_ - yyn + 1;
            int yyxend = yychecklim < yyntokens_ ? yychecklim : yyntokens_;
            for (int yyx = yyxbegin; yyx < yyxend; ++yyx)
              if (yycheck_[yyx + yyn] == yyx && yyx != yyterror_
                  && !yy_table_value_is_error_ (yytable_[yyx + yyn]))
                {
                  if (yycount == YYERROR_VERBOSE_ARGS_MAXIMUM)
                    {
                      yycount = 1;
                      break;
                    }
                  else
                    yyarg[yycount++] = yytname_[yyx];
                }
          }
      }

    char const* yyformat = YY_NULLPTR;
    switch (yycount)
      {
#define YYCASE_(N, S)                         \
        case N:                               \
          yyformat = S;                       \
        break
      default: // Avoid compiler warnings.
        YYCASE_ (0, YY_("syntax error"));
        YYCASE_ (1, YY_("syntax error, unexpected %s"));
        YYCASE_ (2, YY_("syntax error, unexpected %s, expecting %s"));
        YYCASE_ (3, YY_("syntax error, unexpected %s, expecting %s or %s"));
        YYCASE_ (4, YY_("syntax error, unexpected %s, expecting %s or %s or %s"));
        YYCASE_ (5, YY_("syntax error, unexpected %s, expecting %s or %s or %s or %s"));
#undef YYCASE_
      }

    std::string yyres;
    // Argument number.
    size_t yyi = 0;
    for (char const* yyp = yyformat; *yyp; ++yyp)
      if (yyp[0] == '%' && yyp[1] == 's' && yyi < yycount)
        {
          yyres += yytnamerr_ (yyarg[yyi++]);
          ++yyp;
        }
      else
        yyres += *yyp;
    return yyres;
  }


  const signed char Parser::yypact_ninf_ = -24;

  const signed char Parser::yytable_ninf_ = -1;

  const signed char
  Parser::yypact_[] =
  {
     -24,     9,   -24,    -3,   -24,   -24,     2,    52,    -9,    -2,
     -24,    -8,    32,    37,     5,     5,    34,    11,    40,    43,
     -24,   -24,   -24,    51,    45,     3,   -20,     5,    70,    72,
      54,     5,    72,    54,     5,    72,    54,    72,    54,    72,
      54,   -23,   -24,   -24,   -24,   -24,   -24,    74,    50,    75,
      58,    72,    54,    29,    54,    72,    54,    54,    72,    54,
      54,    54,    54,    79,    55,    51,   -24,    64,    83,   -24,
      42,    54,    84,   -24,    54,    54,    -1,    86,   -24,    63,
      66,    58,    67,    71,   -24,    68,     4,    58,    28,   -24,
     -24,   -24,   -24,   -24,    69,    44,   -22,    73,    76,    77,
      80,   -24,    72,   -24,    78,   -24,    82,   -24,   -24,   -24,
     -24,    30,   -24,   -24,    85,   -24
  };

  const unsigned char
  Parser::yydefact_[] =
  {
      51,     0,     1,     0,    46,    52,     0,     0,     0,     0,
      50,     0,     0,     0,     0,     0,     0,     0,     0,     0,
      47,    48,    49,     4,     0,     0,     0,     0,     0,     0,
      16,     0,     0,    20,     0,     0,    24,     0,    28,     0,
      30,     0,    34,    35,    36,     5,    32,     0,     0,     0,
      37,     0,    19,     0,    17,     0,    23,    21,     0,    27,
      25,    29,    31,     0,     0,     6,    33,     0,     0,    38,
       0,    18,     0,     3,    22,    26,     0,     0,     7,     0,
       0,     0,     0,     0,    42,     0,     0,    37,     0,    39,
      40,     2,    44,    43,     0,     0,     0,     0,     0,     0,
       0,    10,     0,    45,     0,     8,     0,    11,    12,    13,
      14,     0,    41,     9,     0,    15
  };

  const signed char
  Parser::yypgoto_[] =
  {
     -24,    18,   -11,    21,   -24,   -24,   -24,   -24,   -24,    23,
     -24,   -24,   -24,   -24,   -24
  };

  const signed char
  Parser::yydefgoto_[] =
  {
      -1,    29,    25,    69,    17,    18,    19,     4,    20,    70,
      21,    22,     7,     5,     1
  };

  const unsigned char
  Parser::yytable_[] =
  {
      30,    33,    36,    38,    40,    23,    23,    28,    28,     2,
      49,     6,    26,    27,   105,    50,    52,    63,    54,    23,
      56,    57,    28,    59,    60,     3,    61,    24,    62,    28,
      32,    35,    37,    39,    28,    28,    47,     8,    84,    48,
      71,    45,    96,    93,    74,    51,    23,    75,    41,    55,
      42,    23,    58,    31,    97,    98,    99,   100,    34,    64,
      72,    73,    28,    47,   101,   102,     9,    28,   114,    10,
      11,    12,    13,    14,    15,    81,    16,    81,    82,    43,
     104,    28,    44,    78,    46,    53,    23,    47,    65,    66,
      67,   111,    68,    76,    85,    77,    79,    80,    87,    83,
      86,    88,    89,    91,    94,     0,    90,    92,   103,   107,
      95,     0,   108,   109,   106,     0,   110,   112,   113,     0,
       0,   115
  };

  const signed char
  Parser::yycheck_[] =
  {
      11,    12,    13,    14,    15,    14,    14,    30,    30,     0,
      30,    14,    14,    21,    36,    35,    27,    40,    29,    14,
      31,    32,    30,    34,    35,    16,    37,    36,    39,    30,
      12,    13,    14,    15,    30,    30,    33,    35,    39,    36,
      51,    23,    14,    39,    55,    27,    14,    58,    14,    31,
      39,    14,    34,    21,    26,    27,    28,    29,    21,    41,
      31,    32,    30,    33,    36,    37,    14,    30,    38,    17,
      18,    19,    20,    21,    22,    33,    24,    33,    36,    39,
      36,    30,    39,    65,    39,    15,    14,    33,    14,    39,
      15,   102,    34,    14,    76,    40,    32,    14,    35,    15,
      14,    35,    81,    32,    86,    -1,    39,    39,    39,    36,
      87,    -1,    36,    36,    96,    -1,    36,    39,    36,    -1,
      -1,    36
  };

  const unsigned char
  Parser::yystos_[] =
  {
       0,    55,     0,    16,    48,    54,    14,    53,    35,    14,
      17,    18,    19,    20,    21,    22,    24,    45,    46,    47,
      49,    51,    52,    14,    36,    43,    14,    21,    30,    42,
      43,    21,    42,    43,    21,    42,    43,    42,    43,    42,
      43,    14,    39,    39,    39,    42,    39,    33,    36,    30,
      35,    42,    43,    15,    43,    42,    43,    43,    42,    43,
      43,    43,    43,    40,    42,    14,    39,    15,    34,    44,
      50,    43,    31,    32,    43,    43,    14,    40,    42,    32,
      14,    33,    36,    15,    39,    42,    14,    35,    35,    44,
      39,    32,    39,    39,    42,    50,    14,    26,    27,    28,
      29,    36,    37,    39,    36,    36,    42,    36,    36,    36,
      36,    43,    39,    36,    38,    36
  };

  const unsigned char
  Parser::yyr1_[] =
  {
       0,    41,    42,    42,    43,    43,    43,    43,    44,    44,
      44,    44,    44,    44,    44,    44,    45,    45,    45,    45,
      45,    45,    45,    45,    45,    45,    45,    45,    46,    46,
      47,    47,    48,    48,    49,    49,    49,    50,    50,    50,
      51,    51,    52,    52,    52,    52,    53,    53,    53,    53,
      54,    55,    55
  };

  const unsigned char
  Parser::yyr2_[] =
  {
       0,     2,     5,     3,     1,     2,     3,     4,     5,     6,
       4,     5,     5,     5,     5,     7,     2,     3,     4,     3,
       2,     3,     4,     3,     2,     3,     4,     3,     2,     3,
       2,     3,     5,     6,     2,     2,     2,     0,     1,     3,
       6,     9,     5,     6,     6,     7,     0,     2,     2,     2,
       3,     0,     2
  };



  // YYTNAME[SYMBOL-NUM] -- String name of the symbol SYMBOL-NUM.
  // First, the terminals, then, starting at \a yyntokens_, nonterminals.
  const char*
  const Parser::yytname_[] =
  {
  "\"end of file\"", "error", "$undefined", "ALWAYS", "EQUAL", "POSEDGE",
  "NEGEDGE", "OR", "BEG", "AND", "IF", "ELSE", "INIT", "AT", "NAME", "NUM",
  "MODULE", "ENDMODULE", "INPUT", "OUTPUT", "INOUT", "REG", "WIRE",
  "INTEGER", "ASSIGN", "TIME", "BIT_MASK", "OCT_MASK", "DEC_MASK",
  "HEX_MASK", "'['", "':'", "']'", "','", "'.'", "'('", "')'", "'{'",
  "'}'", "';'", "'='", "$accept", "range", "general_name_array", "param2",
  "param3", "param4", "param5", "module_declare", "variable_declare",
  "instance_params", "module_instance", "assignment", "module_content",
  "single_module", "start", YY_NULLPTR
  };

#if VERILOGPARSERDEBUG
  const unsigned short
  Parser::yyrline_[] =
  {
       0,   134,   134,   135,   152,   156,   161,   166,   180,   181,
     182,   183,   184,   185,   186,   187,   190,   191,   192,   193,
     194,   195,   196,   197,   198,   199,   200,   201,   204,   205,
     208,   209,   225,   226,   229,   230,   231,   235,   236,   237,
     240,   241,   252,   253,   254,   255,   257,   258,   259,   260,
     264,   267,   268
  };

  // Print the state stack on the debug stream.
  void
  Parser::yystack_print_ ()
  {
    *yycdebug_ << "Stack now";
    for (stack_type::const_iterator
           i = yystack_.begin (),
           i_end = yystack_.end ();
         i != i_end; ++i)
      *yycdebug_ << ' ' << i->state;
    *yycdebug_ << '\n';
  }

  // Report on the debug stream that the rule \a yyrule is going to be reduced.
  void
  Parser::yy_reduce_print_ (int yyrule)
  {
    unsigned yylno = yyrline_[yyrule];
    int yynrhs = yyr2_[yyrule];
    // Print the symbols being reduced, and their result.
    *yycdebug_ << "Reducing stack by rule " << yyrule - 1
               << " (line " << yylno << "):\n";
    // The symbols being reduced.
    for (int yyi = 0; yyi < yynrhs; yyi++)
      YY_SYMBOL_PRINT ("   $" << yyi + 1 << " =",
                       yystack_[(yynrhs) - (yyi + 1)]);
  }
#endif // VERILOGPARSERDEBUG

  Parser::token_number_type
  Parser::yytranslate_ (int t)
  {
    // YYTRANSLATE[TOKEN-NUM] -- Symbol number corresponding to
    // TOKEN-NUM as returned by yylex.
    static
    const token_number_type
    translate_table[] =
    {
       0,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
      35,    36,     2,     2,    33,     2,    34,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,    31,    39,
       2,    40,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,    30,     2,    32,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,    37,     2,    38,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     1,     2,     3,     4,
       5,     6,     7,     8,     9,    10,    11,    12,    13,    14,
      15,    16,    17,    18,    19,    20,    21,    22,    23,    24,
      25,    26,    27,    28,    29
    };
    const unsigned user_token_number_max_ = 284;
    const token_number_type undef_token_ = 2;

    if (static_cast<int> (t) <= yyeof_)
      return yyeof_;
    else if (static_cast<unsigned> (t) <= user_token_number_max_)
      return translate_table[t];
    else
      return undef_token_;
  }

} // VerilogParser
#line 1439 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/verilog/bison/VerilogParser.cc"

#line 273 "VerilogParser.yy"
 /*** Additional Code ***/

void VerilogParser::Parser::error(const Parser::location_type& l,
			    const std::string& m)
{
    driver.error(l, m);
}
