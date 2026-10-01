package UoW::Client;

use strict;
use warnings;
use JSON::PP;
use HTTP::Tiny;

our $VERSION = '1.0.0';

sub new {
    my ($class, %args) = @_;
    my $self = {
        endpoint_url  => $args{endpoint_url} || 'http://localhost:8000/v1/uow',
        default_actor => $args{default_actor} || { id => 'perl-client', claim_type => 'AUTHENTICATED' },
        http          => HTTP::Tiny->new(timeout => $args{timeout} || 10),
        json          => JSON::PP->new->utf8->canonical(1),
    };
    return bless $self, $class;
}

sub execute {
    my ($self, $envelope) = @_;
    my $encoded = $self->{json}->encode($envelope);
    my $response = $self->{http}->post(
        $self->{endpoint_url} . '/execute',
        {
            headers => { 'Content-Type' => 'application/json' },
            content => $encoded,
        }
    );

    if (!$response->{success}) {
        die "HTTP error executing UoW: $response->{status} $response->{reason}\n";
    }

    return $self->{json}->decode($response->{content});
}

1;
