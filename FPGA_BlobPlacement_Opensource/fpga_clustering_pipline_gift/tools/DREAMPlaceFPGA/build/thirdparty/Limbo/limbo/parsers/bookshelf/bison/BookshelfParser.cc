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
#define yylex   BookshelfParserlex

// First part of user prologue.
#line 4 "BookshelfParser.yy"
 /*** C/C++ Declarations ***/

#include <stdio.h>
#include <string>
#include <vector>

/*#include "expression.h"*/


#line 52 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"


#include "BookshelfParser.h"

// Second part of user prologue.
#line 201 "BookshelfParser.yy"


#include "BookshelfDriver.h"
#include "BookshelfScanner.h"

/* this "connects" the bison parser in the driver to the flex scanner class
 * object. it defines the yylex() function call to pull the next token from the
 * current lexer object of the driver context. */
#undef yylex
#define yylex driver.lexer->lex


#line 71 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"



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
#if BOOKSHELFPARSERDEBUG

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

#else // !BOOKSHELFPARSERDEBUG

# define YYCDEBUG if (false) std::cerr
# define YY_SYMBOL_PRINT(Title, Symbol)  YYUSE (Symbol)
# define YY_REDUCE_PRINT(Rule)           static_cast<void> (0)
# define YY_STACK_PRINT()                static_cast<void> (0)

#endif // !BOOKSHELFPARSERDEBUG

#define yyerrok         (yyerrstatus_ = 0)
#define yyclearin       (yyla.clear ())

#define YYACCEPT        goto yyacceptlab
#define YYABORT         goto yyabortlab
#define YYERROR         goto yyerrorlab
#define YYRECOVERING()  (!!yyerrstatus_)

namespace BookshelfParser {
#line 166 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"


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
#if BOOKSHELFPARSERDEBUG
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
      case 6: // "string"
#line 188 "BookshelfParser.yy"
        { delete (yysym.value.stringVal); }
#line 400 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
        break;

      default:
        break;
    }
  }

#if BOOKSHELFPARSERDEBUG
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

#if BOOKSHELFPARSERDEBUG
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
#endif // BOOKSHELFPARSERDEBUG

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
#line 42 "BookshelfParser.yy"
{
    // initialize the initial location object
    yyla.location.begin.filename = yyla.location.end.filename = &driver.streamname;
}

#line 546 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"


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
  case 11:
#line 269 "BookshelfParser.yy"
    { delete (yystack_[3].value.stringVal); }
#line 671 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 14:
#line 274 "BookshelfParser.yy"
    { driver.setLibFileCbk(*(yystack_[0].value.stringVal)); delete (yystack_[0].value.stringVal); }
#line 677 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 15:
#line 275 "BookshelfParser.yy"
    { driver.setSclFileCbk(*(yystack_[0].value.stringVal)); delete (yystack_[0].value.stringVal); }
#line 683 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 16:
#line 276 "BookshelfParser.yy"
    { driver.setNodeFileCbk(*(yystack_[0].value.stringVal)); delete (yystack_[0].value.stringVal); }
#line 689 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 17:
#line 277 "BookshelfParser.yy"
    { driver.setNetFileCbk(*(yystack_[0].value.stringVal)); delete (yystack_[0].value.stringVal); }
#line 695 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 18:
#line 278 "BookshelfParser.yy"
    { driver.setPlFileCbk(*(yystack_[0].value.stringVal)); delete (yystack_[0].value.stringVal); }
#line 701 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 19:
#line 279 "BookshelfParser.yy"
    { driver.setWtFileCbk(*(yystack_[0].value.stringVal)); delete (yystack_[0].value.stringVal); }
#line 707 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 23:
#line 290 "BookshelfParser.yy"
    { driver.nodeEntryCbk(*(yystack_[2].value.stringVal), *(yystack_[1].value.stringVal)); delete (yystack_[2].value.stringVal); delete (yystack_[1].value.stringVal); }
#line 713 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 28:
#line 306 "BookshelfParser.yy"
    { driver.addNetCbk(*(yystack_[2].value.stringVal), (yystack_[1].value.integerVal)); delete (yystack_[2].value.stringVal); }
#line 719 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 29:
#line 309 "BookshelfParser.yy"
    { driver.netEntryCbk(); }
#line 725 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 32:
#line 316 "BookshelfParser.yy"
    { driver.addPinCbk(*(yystack_[2].value.stringVal), *(yystack_[1].value.stringVal)); delete (yystack_[2].value.stringVal); delete (yystack_[1].value.stringVal); }
#line 731 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 40:
#line 387 "BookshelfParser.yy"
    { driver.plNodeEntryCbk(*(yystack_[5].value.stringVal), (yystack_[4].value.integerVal), (yystack_[3].value.integerVal), (yystack_[2].value.integerVal)); delete (yystack_[5].value.stringVal); }
#line 737 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 55:
#line 470 "BookshelfParser.yy"
    { delete (yystack_[0].value.stringVal); }
#line 743 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 63:
#line 493 "BookshelfParser.yy"
    { delete (yystack_[0].value.stringVal); }
#line 749 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 66:
#line 503 "BookshelfParser.yy"
    { driver.routeGridCbk((yystack_[2].value.integerVal), (yystack_[1].value.integerVal)); }
#line 755 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 70:
#line 512 "BookshelfParser.yy"
    { driver.setSiteTypeToSliceLCbk((yystack_[3].value.integerVal), (yystack_[2].value.integerVal)); }
#line 761 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 71:
#line 513 "BookshelfParser.yy"
    { driver.setSiteTypeToDspCbk((yystack_[3].value.integerVal), (yystack_[2].value.integerVal)); }
#line 767 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 72:
#line 514 "BookshelfParser.yy"
    { driver.setSiteTypeToRamCbk((yystack_[3].value.integerVal), (yystack_[2].value.integerVal)); }
#line 773 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 73:
#line 515 "BookshelfParser.yy"
    { driver.setSiteTypeToIoCbk((yystack_[3].value.integerVal), (yystack_[2].value.integerVal)); }
#line 779 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 75:
#line 524 "BookshelfParser.yy"
    { driver.initClockRegionsCbk((yystack_[2].value.integerVal), (yystack_[1].value.integerVal)); }
#line 785 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 79:
#line 534 "BookshelfParser.yy"
    { driver.addClockRegionCbk(*(yystack_[8].value.stringVal), (yystack_[6].value.integerVal), (yystack_[5].value.integerVal), (yystack_[4].value.integerVal), (yystack_[3].value.integerVal), (yystack_[2].value.integerVal), (yystack_[1].value.integerVal)); delete (yystack_[8].value.stringVal); }
#line 791 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 85:
#line 763 "BookshelfParser.yy"
    { driver.addCellCbk(*(yystack_[1].value.stringVal)); delete (yystack_[1].value.stringVal); }
#line 797 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 89:
#line 773 "BookshelfParser.yy"
    { driver.addCellInputPinCbk(*(yystack_[2].value.stringVal));  delete (yystack_[2].value.stringVal); }
#line 803 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 90:
#line 774 "BookshelfParser.yy"
    { driver.addCellOutputPinCbk(*(yystack_[2].value.stringVal)); delete (yystack_[2].value.stringVal); }
#line 809 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 91:
#line 775 "BookshelfParser.yy"
    { driver.addCellClockPinCbk(*(yystack_[3].value.stringVal));  delete (yystack_[3].value.stringVal); }
#line 815 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;

  case 92:
#line 776 "BookshelfParser.yy"
    { driver.addCellCtrlPinCbk(*(yystack_[3].value.stringVal));   delete (yystack_[3].value.stringVal); }
#line 821 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"
    break;


#line 825 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"

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


  const signed char Parser::yypact_ninf_ = -50;

  const signed char Parser::yytable_ninf_ = -1;

  const signed char
  Parser::yypact_[] =
  {
       8,   -50,    20,    10,     1,   -50,   -50,    -1,    33,    16,
      23,   -50,   -50,   -50,   -50,    57,   -50,   -50,    42,   -50,
      59,   -50,   -50,    60,   -50,   -50,    45,   -50,    18,   -50,
     -50,    51,   -50,    52,    64,     8,    13,   -50,   -50,   -50,
     -50,    67,    68,    69,    66,   -50,   -50,    70,     4,   -50,
      73,   -50,    71,   -50,    72,    18,   -50,   -50,     9,   -50,
      74,   -50,    75,    11,   -50,    78,   -50,   -50,   -50,   -50,
     -50,   -50,   -50,    -2,   -50,   -50,   -50,    76,    80,     8,
     -50,   -50,   -50,    81,    61,    83,    82,    34,   -50,    77,
     -50,   -50,    86,    43,    79,   -50,   -50,    84,   -50,    10,
     -50,   -50,   -50,    87,    88,   -50,    85,    89,    53,   -50,
     -50,     6,    90,   -50,   -50,     8,   -50,     5,    91,     8,
       8,    93,    94,    95,    -5,   -50,    44,    92,   -50,   -50,
     -50,   -50,     8,   -50,   -50,    99,   100,   -50,   -50,   -50,
     -50,   102,    96,    97,   -50,   -50,   103,   104,   105,   107,
       8,   -50,   -50,   -50,   -50,   108,     8,   -50,   -50,   -50,
     -50,   -50,   109,   -50,   110,   113,   114,   115,   117,   -50
  };

  const unsigned char
  Parser::yydefact_[] =
  {
      36,    34,     0,    35,    36,     1,    33,     0,     0,     0,
       0,     2,     3,    10,     6,    20,    22,     8,    24,    26,
       0,    80,     7,    37,    39,     5,     0,    44,     0,     9,
       4,    81,    83,     0,     0,    36,     0,    47,    48,    49,
      50,     0,     0,     0,     0,    21,    25,     0,     0,    31,
       0,    38,     0,    43,     0,     0,    55,    56,     0,    53,
       0,    82,     0,     0,    88,     0,    23,    14,    15,    16,
      17,    18,    19,     0,    13,    46,    85,     0,     0,    36,
      27,    30,    58,     0,    41,     0,     0,     0,    61,     0,
      45,    52,     0,     0,     0,    84,    87,     0,    12,    11,
      28,    32,    29,     0,     0,    42,     0,     0,     0,    69,
      64,     0,     0,    57,    60,    36,    54,     0,     0,    36,
      36,     0,     0,     0,     0,    78,     0,     0,    65,    68,
      62,    63,    36,    51,    89,     0,     0,    90,    86,    40,
      66,     0,     0,     0,    74,    77,     0,     0,     0,     0,
      36,    59,    91,    92,    75,     0,    36,    70,    71,    72,
      73,    67,     0,    76,     0,     0,     0,     0,     0,    79
  };

  const signed char
  Parser::yypgoto_[] =
  {
     -50,   -50,   -50,   -50,   -50,   -50,    24,   -50,   -50,   106,
     -50,   -50,   111,   -50,   -50,   -50,    36,    50,    -4,   -50,
     -50,   101,   -50,   -50,   112,   -50,   -50,   -50,   -50,    98,
     -49,   -50,   -50,   -50,   -50,    38,   -50,   -50,   -50,   -50,
     -50,    19,   -50,   -50,   -50,   -50,     2,   -50,   -50,   -50,
     116,   -50,   -50,   -50,   118
  };

  const short
  Parser::yydefgoto_[] =
  {
      -1,     2,    11,    12,    13,    73,    74,    14,    15,    16,
      17,    18,    19,    20,    80,    48,    49,     3,     4,    22,
      23,    24,    25,    26,    27,    28,    41,    90,    58,    59,
      60,    54,    55,   113,    87,    88,   111,    84,    85,   128,
     108,   109,   105,   106,   144,   124,   125,    29,    30,    31,
      32,    33,    95,    63,    64
  };

  const unsigned char
  Parser::yytable_[] =
  {
      21,     1,   143,    34,     1,    35,    86,     7,   134,   130,
      47,     1,   131,     6,     8,    56,    89,     9,    94,   123,
       5,    57,    42,    10,    56,   135,   136,    79,    62,    43,
      57,    66,    67,    68,    69,    70,    71,    72,    86,    36,
      56,   112,    37,    38,    39,    40,    57,    67,    68,    69,
      70,    71,    72,   146,   147,   148,   149,   107,     8,    52,
     127,   117,   118,    44,    10,    47,    50,     9,    65,    62,
      75,    76,    35,    77,    82,   102,    78,    34,    92,   100,
      83,    93,    97,   101,    81,   103,   104,   107,   110,   116,
     115,   121,   122,   126,   137,   119,   140,    98,   141,   120,
     150,   142,   152,   153,   132,   154,   157,   158,   159,   123,
     160,   133,   162,   164,   165,   138,   139,   166,   167,   168,
     169,    45,   156,    99,    51,   114,   145,   129,   151,    46,
       0,     0,     0,     0,     0,     0,   155,     0,    53,     0,
       0,     0,     0,     0,     0,     0,   161,    61,     0,     0,
       0,     0,   163,     0,     0,     0,    91,     0,     0,     0,
       0,     0,     0,     0,     0,     0,     0,     0,     0,     0,
       0,     0,     0,     0,     0,     0,     0,     0,     0,     0,
       0,    96
  };

  const short
  Parser::yycheck_[] =
  {
       4,     3,     7,     4,     3,     6,    55,     6,     3,     3,
       6,     3,     6,     3,    13,     6,     7,    16,     7,    24,
       0,    12,     6,    22,     6,    20,    21,    23,    17,     6,
      12,    35,    34,    35,    36,    37,    38,    39,    87,    40,
       6,     7,     9,    10,    11,    12,    12,    34,    35,    36,
      37,    38,    39,     9,    10,    11,    12,     4,    13,    14,
       7,    18,    19,     6,    22,     6,     6,    16,     4,    17,
       3,     3,     6,     4,     3,    79,     6,     4,     4,     3,
       8,     6,     4,     3,    48,     4,    25,     4,     6,     3,
      13,     4,     4,     4,     3,    16,     3,    73,     4,    15,
       8,     6,     3,     3,    14,     3,     3,     3,     3,    24,
       3,   115,     4,     4,     4,   119,   120,     4,     4,     4,
       3,    15,    25,    73,    23,    87,   124,   108,   132,    18,
      -1,    -1,    -1,    -1,    -1,    -1,    40,    -1,    26,    -1,
      -1,    -1,    -1,    -1,    -1,    -1,   150,    31,    -1,    -1,
      -1,    -1,   156,    -1,    -1,    -1,    58,    -1,    -1,    -1,
      -1,    -1,    -1,    -1,    -1,    -1,    -1,    -1,    -1,    -1,
      -1,    -1,    -1,    -1,    -1,    -1,    -1,    -1,    -1,    -1,
      -1,    63
  };

  const unsigned char
  Parser::yystos_[] =
  {
       0,     3,    42,    58,    59,     0,     3,     6,    13,    16,
      22,    43,    44,    45,    48,    49,    50,    51,    52,    53,
      54,    59,    60,    61,    62,    63,    64,    65,    66,    88,
      89,    90,    91,    92,     4,     6,    40,     9,    10,    11,
      12,    67,     6,     6,     6,    50,    53,     6,    56,    57,
       6,    62,    14,    65,    72,    73,     6,    12,    69,    70,
      71,    91,    17,    94,    95,     4,    59,    34,    35,    36,
      37,    38,    39,    46,    47,     3,     3,     4,     6,    23,
      55,    57,     3,     8,    78,    79,    71,    75,    76,     7,
      68,    70,     4,     6,     7,    93,    95,     4,    47,    58,
       3,     3,    59,     4,    25,    83,    84,     4,    81,    82,
       6,    77,     7,    74,    76,    13,     3,    18,    19,    16,
      15,     4,     4,    24,    86,    87,     4,     7,    80,    82,
       3,     6,    14,    59,     3,    20,    21,     3,    59,    59,
       3,     4,     6,     7,    85,    87,     9,    10,    11,    12,
       8,    59,     3,     3,     3,    40,    25,     3,     3,     3,
       3,    59,     4,    59,     4,     4,     4,     4,     4,     3
  };

  const unsigned char
  Parser::yyr1_[] =
  {
       0,    41,    42,    43,    43,    43,    43,    43,    43,    43,
      44,    45,    46,    46,    47,    47,    47,    47,    47,    47,
      48,    49,    49,    50,    51,    52,    52,    53,    54,    55,
      56,    56,    57,    58,    58,    59,    59,    60,    61,    61,
      62,    63,    63,    64,    64,    65,    66,    67,    67,    67,
      67,    68,    69,    69,    70,    71,    71,    72,    73,    74,
      75,    75,    76,    77,    77,    78,    79,    80,    81,    81,
      82,    82,    82,    82,    83,    84,    85,    86,    86,    87,
      88,    89,    90,    90,    91,    92,    93,    94,    94,    95,
      95,    95,    95
  };

  const unsigned char
  Parser::yyr2_[] =
  {
       0,     2,     2,     1,     1,     1,     1,     1,     1,     1,
       1,     4,     2,     1,     1,     1,     1,     1,     1,     1,
       1,     2,     1,     3,     1,     2,     1,     3,     4,     2,
       2,     1,     3,     2,     1,     1,     0,     1,     2,     1,
       6,     3,     4,     2,     1,     3,     3,     1,     1,     1,
       1,     3,     2,     1,     3,     1,     1,     3,     2,     3,
       2,     1,     3,     2,     1,     3,     4,     3,     2,     1,
       4,     4,     4,     4,     3,     4,     3,     2,     1,    10,
       1,     1,     2,     1,     3,     3,     3,     2,     1,     4,
       4,     5,     5
  };



  // YYTNAME[SYMBOL-NUM] -- String name of the symbol SYMBOL-NUM.
  // First, the terminals, then, starting at \a yyntokens_, nonterminals.
  const char*
  const Parser::yytname_[] =
  {
  "\"end of file\"", "error", "$undefined", "\"end of line\"",
  "\"integer\"", "\"double\"", "\"string\"", "\"END\"", "\"SITEMAP\"",
  "\"SLICE\"", "\"DSP\"", "\"BRAM\"", "\"IO\"", "\"SITE\"",
  "\"RESOURCES\"", "\"FIXED\"", "\"CELL\"", "\"PIN\"", "\"INPUT\"",
  "\"OUTPUT\"", "\"CLOCK\"", "\"CTRL\"", "\"net\"", "\"endnet\"",
  "\"CLOCKREGION\"", "\"CLOCKREGIONS\"", "\"Type\"", "\"lib\"", "\"scl\"",
  "\"nodes\"", "\"nets\"", "\"pl\"", "\"wts\"", "\"aux\"", "LIB_FILE",
  "SCL_FILE", "NODE_FILE", "NET_FILE", "PL_FILE", "WT_FILE", "':'",
  "$accept", "start", "sub_top", "aux_top", "aux_line", "aux_files",
  "aux_file", "node_top", "node_lines", "node_line", "net_top",
  "net_blocks", "net_block", "net_block_header", "net_block_footer",
  "net_block_lines", "net_block_line", "EOLS", "EOL_STAR", "pl_top",
  "pl_lines", "pl_line", "scl_top", "site_blocks", "site_block",
  "site_block_header", "site_type_name", "site_block_footer",
  "site_block_lines", "site_block_line", "rsrc_type_name", "rsrc_block",
  "rsrc_block_header", "rsrc_block_footer", "rsrc_block_lines",
  "rsrc_block_line", "cell_name_list", "sitemap_block",
  "sitemap_block_header", "sitemap_block_footer", "sitemap_block_lines",
  "sitemap_block_line", "clock_region_block", "clock_region_block_header",
  "clock_region_block_footer", "clock_region_block_lines",
  "clock_region_block_line", "wt_top", "lib_top", "cell_blocks",
  "cell_block", "cell_block_header", "cell_block_footer",
  "cell_block_lines", "cell_block_line", YY_NULLPTR
  };

#if BOOKSHELFPARSERDEBUG
  const unsigned short
  Parser::yyrline_[] =
  {
       0,   243,   243,   246,   247,   248,   249,   250,   251,   252,
     266,   269,   271,   272,   274,   275,   276,   277,   278,   279,
     283,   286,   287,   290,   294,   297,   298,   301,   306,   309,
     312,   313,   316,   320,   321,   324,   325,   380,   383,   384,
     387,   438,   439,   442,   443,   446,   451,   454,   455,   456,
     457,   460,   463,   464,   467,   470,   471,   475,   480,   483,
     486,   487,   490,   493,   494,   498,   503,   505,   508,   509,
     512,   513,   514,   515,   519,   524,   527,   530,   531,   534,
     590,   751,   754,   755,   758,   763,   766,   769,   770,   773,
     774,   775,   776
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
#endif // BOOKSHELFPARSERDEBUG

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
       2,     2,     2,     2,     2,     2,     2,     2,     2,     2,
       2,     2,     2,     2,     2,     2,     2,     2,    40,     2,
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
      25,    26,    27,    28,    29,    30,    31,    32,    33,    34,
      35,    36,    37,    38,    39
    };
    const unsigned user_token_number_max_ = 294;
    const token_number_type undef_token_ = 2;

    if (static_cast<int> (t) <= yyeof_)
      return yyeof_;
    else if (static_cast<unsigned> (t) <= user_token_number_max_)
      return translate_table[t];
    else
      return undef_token_;
  }

} // BookshelfParser
#line 1395 "/work/fpga_clustering_pipline_gift/tools/DREAMPlaceFPGA/build/thirdparty/Limbo/limbo/parsers/bookshelf/bison/BookshelfParser.cc"

#line 781 "BookshelfParser.yy"
 /*** Additional Code ***/

void BookshelfParser::Parser::error(const Parser::location_type& l,
			    const std::string& m)
{
    driver.error(l, m);
    exit(1);
}
