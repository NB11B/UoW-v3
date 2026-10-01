#!/usr/bin/env perl
use strict;
use warnings;
use FindBin;
use lib "$FindBin::Bin/../../legacy/perl";
use JSON::PP;

print "=== UoW Polyglot Interoperability Demo (Perl) ===\n";

my $envelope = {
    protocol_version  => '1.0.0',
    operation         => 'inventory.reserve',
    operation_version => '1.0.0',
    request_id        => 'req-perl-001',
    correlation_id    => 'corr-perl-001',
    actor => {
        id         => 'legacy-perl-daemon',
        claim_type => 'AUTHENTICATED',
    },
    payload => {
        sku      => 'WIDGET-99',
        quantity => 1,
        order_id => 'ORD-PERL-99',
    },
    constraints => {
        idempotency_key => 'idem-perl-99',
    },
};

my $json = JSON::PP->new->utf8->canonical(1)->pretty(1);
print "Serialized Perl Wire Request:\n" . $json->encode($envelope);
