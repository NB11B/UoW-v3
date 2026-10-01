#!/usr/bin/env perl
use strict;
use warnings;
use Test::More;
use File::Basename;
use File::Spec;
use JSON::PP;

my $script_dir = dirname(__FILE__);
my @candidates = (
    File::Spec->rel2abs(File::Spec->catdir($script_dir, '..', '..', '..', '..', 'conformance', 'vectors')),
    File::Spec->rel2abs(File::Spec->catdir($script_dir, '..', '..', '..', 'conformance', 'vectors')),
);
my $vectors_dir;
for my $c (@candidates) {
    if (-d $c) { $vectors_dir = $c; last; }
}
$vectors_dir //= $candidates[0];

opendir(my $dh, $vectors_dir) or die "Cannot open $vectors_dir: $!\n";
my @files = sort grep { /\.json$/ } readdir($dh);
closedir($dh);

ok(scalar(@files) >= 16, "Found at least 16 golden conformance vectors in Perl runner");

my $json = JSON::PP->new->utf8->canonical(1);

for my $file (@files) {
    my $path = File::Spec->catfile($vectors_dir, $file);
    open(my $fh, '<:raw', $path) or die "Cannot read $path: $!\n";
    local $/;
    my $content = <$fh>;
    close($fh);

    my $vector = $json->decode($content);
    my $id = $vector->{vector_id};
    ok(defined $id, "Vector $file defines vector_id");

    if ($vector->{input} && $vector->{input}->{envelope}) {
        my $env = $vector->{input}->{envelope};
        ok(defined $env->{protocol_version}, "Vector $id envelope has protocol_version");
        ok(defined $env->{operation}, "Vector $id envelope has operation");
        
        # Test wire canonical round-trip in Perl
        my $encoded = $json->encode($env);
        my $roundtrip = $json->decode($encoded);
        is_deeply($roundtrip, $env, "Vector $id roundtrips cleanly in Perl JSON::PP");
    }
}

done_testing();
