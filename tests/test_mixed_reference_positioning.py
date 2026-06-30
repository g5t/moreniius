"""Tests for positioning with mixed or cross-reference AT/ROTATED clauses."""


def build_instrument():
    from mccode_antlr import Flavor
    from mccode_antlr.assembler import Assembler

    a = Assembler('test', flavor=Flavor.MCSTAS)
    a.component('origin', 'Arm', at=(0, 0, 0))
    # A is tilted 45° and displaced 1m from origin
    a.component('A', 'Arm', at=[(0, 0, 1), 'origin'], rotate=[(0, 45, 0), 'origin'])
    # B is another 45° tilt further along A's axis (cumulative Ry(90°) from world)
    a.component('B', 'Arm', at=[(0, 0, 1), 'A'], rotate=[(0, 45, 0), 'A'])
    # AT ABSOLUTE, ROTATED RELATIVE A: non-zero position in world frame, rotation from A's chain
    a.component('at_abs', 'Arm', at=(0, 0, 2), rotate=[(0, 45, 0), 'A'])
    # AT (0,0,0) ABSOLUTE, ROTATED RELATIVE A: zero position anchored at world origin
    a.component('at_abs_zero', 'Arm', at=(0, 0, 0), rotate=[(0, 45, 0), 'A'])
    # AT RELATIVE origin, ROTATED RELATIVE B: different references with B having a non-trivial chain
    a.component('diff_ref', 'Arm', at=[(0, 0, 3), 'origin'], rotate=[(0, 0, 0), 'B'])
    # AT (0,0,0) RELATIVE A, ROTATED RELATIVE A: zero position must still chain from A
    a.component('zero_pos', 'Arm', at=[(0, 0, 0), 'A'], rotate=[(0, 45, 0), 'A'])
    return a.instrument


def dep_of(nx_transforms, name):
    return nx_transforms[name].attrs['depends_on']


def find_translations(nx_transforms):
    """Return a list of (name, field) pairs for all translation-type entries."""
    return [
        (k, v) for k, v in nx_transforms.items()
        if v.attrs.get('transformation_type') == 'translation'
    ]


def test_at_absolute_translation_depends_on_world():
    """AT ABSOLUTE translation must anchor to '.' (world frame), not to the rotation reference's chain.

    Regression test for the bug where position_transformations was called with target=resolve_target(rot_rel),
    which caused the translation vector to be interpreted in rot_rel's rotated coordinate frame.
    """
    import moreniius

    me = moreniius.MorEniius.from_mccode(build_instrument(), origin='origin')
    trans = me.nx['at_abs']['transformations']

    translations = find_translations(trans)
    assert translations, "AT ABSOLUTE component must have at least one translation entry"
    # The outermost translation (dep='.') must depend directly on the world frame
    outermost = next((name for name, _ in translations if dep_of(trans, name) == '.'), None)
    assert outermost is not None, (
        "AT ABSOLUTE translation must depend on '.' (world frame), "
        f"not on the rotation reference's last transformation. Found deps: "
        f"{[(n, dep_of(trans, n)) for n, _ in translations]}"
    )


def test_at_absolute_rotation_chains_from_translation():
    """The rotation bridge for AT ABSOLUTE ROTATED RELATIVE A must chain from the translation."""
    import moreniius

    me = moreniius.MorEniius.from_mccode(build_instrument(), origin='origin')
    trans = me.nx['at_abs']['transformations']

    # Find the outermost (world-anchored) translation
    translations = find_translations(trans)
    outermost_t = next(name for name, _ in translations if dep_of(trans, name) == '.')

    # A_r0 (in at_abs's own group) must chain from the component's own translation
    a_r0_dep = dep_of(trans, 'A_r0')
    assert a_r0_dep == outermost_t, f"A_r0 must depend on '{outermost_t}', got '{a_r0_dep}'"
    # at_abs's own local rotation depends on A_r0 in the same group
    assert dep_of(trans, 'at_abs_r0') == 'A_r0'


def test_different_references_chain_is_self_contained():
    """AT RELATIVE orig ROTATED RELATIVE B must produce a chain fully within the component's group.

    When at_ref ≠ rot_ref and rot_ref has a non-trivial existing transformation chain,
    the rotation entries in the new component's group must use freshly-created NXfields
    (with the correct dep) rather than pointers into the rotation reference's chain.
    """
    import moreniius

    me = moreniius.MorEniius.from_mccode(build_instrument(), origin='origin')
    trans = me.nx['diff_ref']['transformations']

    # Translation is relative to origin (which has no transforms) → dep='.'
    translations = find_translations(trans)
    assert translations, "diff_ref must have at least one translation entry"
    outermost_t = next(name for name, _ in translations if dep_of(trans, name) == '.')

    # B's cumulative rotation is replicated as a fresh entry chaining from the translation
    b_r0_dep = dep_of(trans, 'B_r0')
    assert b_r0_dep == outermost_t, (
        f"B's rotation must chain from '{outermost_t}' (the component's own translation), "
        f"not through B's existing transformation group. Got dep='{b_r0_dep}'"
    )


def test_at_absolute_zero_position_rotation_depends_on_world():
    """AT (0,0,0) ABSOLUTE ROTATED RELATIVE A: with no translation, rotation must chain from '.'

    When position is zero the translation list is empty. The rotation reference's last transformation
    must NOT be used as the chain anchor — the component is at the world origin, not at A's position.
    """
    import moreniius

    me = moreniius.MorEniius.from_mccode(build_instrument(), origin='origin')
    trans = me.nx['at_abs_zero']['transformations']

    # No translations should be present
    translations = find_translations(trans)
    assert not translations, f"AT (0,0,0) ABSOLUTE should produce no translations, got {[n for n, _ in translations]}"

    # The rotation must chain from '.' (world frame), not from A's transformation path
    rotations = [(k, v) for k, v in trans.items() if v.attrs.get('transformation_type') == 'rotation']
    assert rotations, "AT ABSOLUTE ROTATED RELATIVE A must still produce rotation entries"
    outermost_rot_dep = dep_of(trans, rotations[0][0])
    assert outermost_rot_dep == '.', (
        f"AT (0,0,0) ABSOLUTE rotation must depend on '.' (world frame), got '{outermost_rot_dep}'"
    )


def test_zero_position_same_reference_chains_from_reference():
    """AT (0,0,0) RELATIVE A ROTATED RELATIVE A must chain from A, not from the world frame.

    When the position is zero (no translation entries produced), last_ref must fall back to
    A's last transformation path so the rotation is expressed in A's coordinate system.
    """
    import moreniius

    me = moreniius.MorEniius.from_mccode(build_instrument(), origin='origin')
    trans = me.nx['zero_pos']['transformations']

    dep = dep_of(trans, 'zero_pos_r0')
    assert dep != '.', "Zero-position same-reference rotation must NOT depend on world frame"
    assert dep.startswith('/entry/instrument/A/transformations/'), (
        f"Zero-position rotation must chain from A's transformations, got dep='{dep}'"
    )
