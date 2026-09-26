/* Chương trình mẫu: đủ các loại nguyên công để thử nhanh. */
#include "core.h"

int demo_ops(const Section *s, Operation *ops)
{
    int n = 0;
    Operation o = {0};
    o.enabled = 1;
    if (s->kind == SEC_ROUND) {
        o.kind = OP_HOLE;   o.x = 60;  o.theta = 0;   o.a = 20;               ops[n++] = o;
        o.kind = OP_HOLE;   o.x = 60;  o.theta = 180; o.a = 20;               ops[n++] = o;
    } else {
        o.kind = OP_CIRCLE; o.x = 60;  o.theta = 0;   o.a = 20;               ops[n++] = o;
        o.kind = OP_CIRCLE; o.x = 60;  o.theta = 90;  o.a = 16;               ops[n++] = o;
    }
    o.kind = OP_SLOT;   o.x = 130; o.theta = 0; o.a = 50; o.b = 60; o.c = 5; ops[n++] = o;
    o.kind = OP_CUTOFF; o.x = 200; o.theta = 0; o.a = 0; o.b = 0; o.c = 0;  ops[n++] = o;
    return n;
}
