# Repair the comment banners of Vivado-generated HDL files.
#
# Vivado writes a "Host : <name> running <OS description>" line into the
# comment banner of every HDL file it generates (block design netlists, HDL
# wrappers, out-of-context black-box stubs, ...). On an OS that Vivado 2026.1
# does not recognise (Ubuntu newer than 24.04, run natively) the rest of
# /etc/os-release spills out as bare source lines right after the Host line
# and synthesis dies with "syntax error near 'VERSION_ID'".
#
# fix_banners walks a directory tree and comments out those spilled lines:
# everything between a Host line in a file's header and the next comment line.
# On a healthy banner the next line is already a comment, so nothing changes.
# Sourced by go.tcl and by the pre-synthesis hook it installs on synth_1.
proc fix_banners {dir} {
    foreach f [glob -nocomplain -directory $dir -types f *] {
        if {![regexp {\.(vhdl?|s?v)$} $f]} continue
        set fh [open $f r]; set lines [split [read $fh] "\n"]; close $fh
        set host [lsearch -regexp [lrange $lines 0 15] {^\s*(--|//)\s*Host\s*:}]
        if {$host < 0} continue
        set tok [expr {[regexp {\.vhdl?$} $f] ? "--" : "//"}]
        set changed 0
        for {set i [expr {$host + 1}]} {$i < [llength $lines]} {incr i} {
            set l [string trimleft [lindex $lines $i]]
            if {[string match "${tok}*" $l]} break
            lset lines $i "$tok $l"; set changed 1
        }
        if {$changed} {
            set fh [open $f w]; puts -nonewline $fh [join $lines "\n"]; close $fh
            puts "fix_banners: repaired $f"
        }
    }
    foreach d [glob -nocomplain -directory $dir -types d *] { fix_banners $d }
}
