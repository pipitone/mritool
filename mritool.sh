
_mritool()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -eq 1 ]; then
        COMPREPLY=( $( compgen -W ' pull sync-exams complete pfile-headers list-inprocess list-exams list-series check' -- $cur) )
    else
        case ${COMP_WORDS[1]} in
            pull)
            _mritool_pull
        ;;
            sync-exams)
            _mritool_sync-exams
        ;;
            complete)
            _mritool_complete
        ;;
            pfile-headers)
            _mritool_pfile-headers
        ;;
            list-inprocess)
            _mritool_list-inprocess
        ;;
            list-exams)
            _mritool_list-exams
        ;;
            list-series)
            _mritool_list-series
        ;;
            check)
            _mritool_check
        ;;
        esac

    fi
}

_mritool_pull()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 2 ]; then
        COMPREPLY=( $( compgen -fW '-o= --bare ' -- $cur) )
    fi
}

_mritool_sync-exams()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 2 ]; then
        COMPREPLY=( $( compgen -W ' ' -- $cur) )
    fi
}

_mritool_complete()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 2 ]; then
        COMPREPLY=( $( compgen -fW ' ' -- $cur) )
    fi
}

_mritool_pfile-headers()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 2 ]; then
        COMPREPLY=( $( compgen -fW ' ' -- $cur) )
    fi
}

_mritool_list-inprocess()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 2 ]; then
        COMPREPLY=( $( compgen -W ' ' -- $cur) )
    fi
}

_mritool_list-exams()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 2 ]; then
        COMPREPLY=( $( compgen -W '-b= -e= -d= ' -- $cur) )
    fi
}

_mritool_list-series()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 2 ]; then
        COMPREPLY=( $( compgen -fW ' ' -- $cur) )
    fi
}

_mritool_check()
{
    local cur
    cur="${COMP_WORDS[COMP_CWORD]}"

    if [ $COMP_CWORD -ge 2 ]; then
        COMPREPLY=( $( compgen -fW ' ' -- $cur) )
    fi
}

complete -F _mritool mritool